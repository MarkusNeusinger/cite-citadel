"""Tests for PR6 `citadel curate` + `citadel status` + MCP/CLI parity (docs/refactor-plan.md
Z5, Z11, Z6).

Covers the whole surface: the offline detectors, the recompute-per-run plan, the
``--dry-run``/``--limit``/``--stale-rules``/``--diff`` driver, the attempt-capped revert-and-stop
cluster sessions, ``citadel status``, the CLI read/index/sources parity + the ``wiki_lint`` MCP
tool, and the Z6 locator lint checks. Each test imports the surface it exercises inside the test
body, so a collection stays green even mid-refactor.

All offline: the agent bridge is the conftest ``fake_agent`` (no real CLI is ever spawned); the
detectors and status readers are pure functions over a seeded ``tmp_citadel`` wiki + manifest.
"""

from __future__ import annotations

import argparse
import asyncio

from citadel import cli, config, lint, manifest, server


# --- seed helpers ---------------------------------------------------------------------------


def _seed_cited(
    seed_page,
    rel_path: str,
    resource: str,
    *,
    type_: str = "Concept",
    title: str = "Topic",
    body_fact: str = "A sourced fact.",
    timestamp: str | None = None,
    trailer: str = "",
) -> None:
    """Seed one valid OKF page whose single fact cites ``resource`` (a ``raw/…`` key), routed
    under ``rel_path``. ``trailer`` appends extra body markup (a second link, an [^llm] fact, a
    contradiction callout) before the ``## Sources`` section."""
    fm = {"type": type_, "title": title, "description": "d", "tags": ["t"], "resource": resource}
    if timestamp is not None:
        fm["timestamp"] = timestamp
    body = (
        f"{body_fact}[^s1]\n{trailer}\n\n## Sources\n\n"
        f"[^s1]: [{resource}](../../{resource}) - s (ingested 2026-06-21)\n"
    )
    seed_page(rel_path, fm, body)


def _track(key: str, sha: str, rules_version: str | None) -> None:
    """Record a manifest entry for a raw source ``key`` (load-modify-save), stamping ``sha`` and
    the effective-rules hash the importing session ran under — what curate's rules-drift and
    stale-reverify detectors read."""
    tracked = manifest.load()
    tracked[key] = manifest.make_entry(sha, "claude:sonnet", rules_version)
    manifest.save(tracked)


def _plan_pages(plan) -> set[str]:
    return {item.page for item in plan.items}


def _reasons_for(plan, page: str) -> set[str]:
    return {r for item in plan.items if item.page == page for r in item.reasons}


# --- offline detectors: each detector, one focused test ---


def test_detector_flags_rules_version_drift(tmp_citadel, seed_page):
    """A page whose source was ingested under an OLDER effective-rules hash than the current one
    is flagged for a re-curate pass (the manifest stamp vs config.rules_version())."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/topic.md", "raw/notes.md")
    _track("raw/notes.md", manifest.file_sha256(tmp_citadel.raw / "notes.md"), "0000oldrules")

    plan = curate.build_plan()
    assert "concepts/topic.md" in _plan_pages(plan)
    assert "rules_version_drift" in _reasons_for(plan, "concepts/topic.md")


def test_detector_flags_overlong_page_at_hard_threshold(tmp_citadel, seed_page):
    """Curate ACTS at the hard page-length threshold (~800 lines) — lint only warns at the soft
    one — so an oversized page is planned for a split."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    long_body = "".join(f"Line {i} of a very long page.[^s1]\n\n" for i in range(900))
    seed_page(
        "concepts/huge.md",
        {"type": "Concept", "title": "Huge", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        f"{long_body}## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n",
    )

    plan = curate.build_plan()
    assert "page_length_hard" in _reasons_for(plan, "concepts/huge.md")


def test_detector_flags_unresolved_contradiction(tmp_citadel, seed_page):
    """A page carrying a `> [!CONTRADICTION]` callout with no resolution line is planned for a
    curate pass (attempt a confident resolution, per schema.md § Contradictions)."""
    from citadel import curate

    (tmp_citadel.raw / "a.md").write_text("body\n", encoding="utf-8")
    _seed_cited(
        seed_page,
        "concepts/clash.md",
        "raw/a.md",
        trailer="\n> [!CONTRADICTION]\n> raw/a.md reports 12% [^s1], but the page said 9%.",
    )

    plan = curate.build_plan()
    assert "contradiction" in _reasons_for(plan, "concepts/clash.md")


def test_detector_flags_orphan_page(tmp_citadel, seed_page):
    """A page nothing links to and that links to nothing (an island) is planned for cross-linking."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/island.md", "raw/notes.md")

    plan = curate.build_plan()
    assert "orphan" in _reasons_for(plan, "concepts/island.md")


def test_detector_flags_llm_drift_outlier(tmp_citadel, seed_page):
    """A page dominated by model-supplied `[^llm]` facts with little-to-no `[^sN]` grounding is a
    per-page drift-ratio outlier — planned for re-grounding against its sources."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    body = (
        "Sourced.[^s1]\n\n"
        "Claim one.[^llm1]\n\nClaim two.[^llm2]\n\nClaim three.[^llm3]\n\nClaim four.[^llm4]\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - s\n"
        "[^llm1]: LLM - model knowledge\n[^llm2]: LLM - model knowledge\n"
        "[^llm3]: LLM - model knowledge\n[^llm4]: LLM - model knowledge\n"
    )
    seed_page(
        "concepts/drifted.md",
        {"type": "Concept", "title": "Drifted", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        body,
    )

    plan = curate.build_plan()
    assert "llm_drift" in _reasons_for(plan, "concepts/drifted.md")


def test_detector_flags_type_folder_mismatch_for_resort(tmp_citadel, seed_page):
    """A page whose `type` routes to a different folder than the one it sits in (okf.folder_for_type)
    is planned for a re-sort — the owner's 'Information umsortieren', made concrete."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    # A Person page mis-filed under concepts/ (folder_for_type("Person") == "persons").
    _seed_cited(seed_page, "concepts/alice.md", "raw/notes.md", type_="Person", title="Alice")

    plan = curate.build_plan()
    assert "resort" in _reasons_for(plan, "concepts/alice.md")


def test_reverify_candidates_are_prefiltered_to_sha_unchanged_sources(tmp_citadel, seed_page):
    """Fact re-verification is pre-filtered offline via manifest shas: a source whose bytes
    CHANGED is reconcile's job, a source that is GONE is delete's job — only sha-UNCHANGED tracked
    sources need the agent's entailment pass, so only they are re-verify candidates."""
    from citadel import curate

    (tmp_citadel.raw / "same.md").write_text("stable\n", encoding="utf-8")
    (tmp_citadel.raw / "changed.md").write_text("new bytes\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/same.md", "raw/same.md")
    _seed_cited(seed_page, "concepts/changed.md", "raw/changed.md", title="Changed")
    _seed_cited(seed_page, "concepts/gone.md", "raw/gone.md", title="Gone")  # source never on disk
    _track("raw/same.md", manifest.file_sha256(tmp_citadel.raw / "same.md"), config.rules_version())
    _track("raw/changed.md", "deadbeef" * 8, config.rules_version())  # manifest sha != file sha
    _track("raw/gone.md", "cafef00d" * 8, config.rules_version())  # file vanished

    candidates = curate.reverify_candidates()
    assert "raw/same.md" in candidates
    assert "raw/changed.md" not in candidates  # changed -> reconcile
    assert "raw/gone.md" not in candidates  # gone -> delete


# --- the plan: recompute per run, --dry-run zero sessions, --limit, --stale-rules ------------


def test_dry_run_recomputes_plan_and_runs_zero_agent_sessions(tmp_citadel, seed_page, fake_agent):
    """There is NO persisted queue: --dry-run recomputes the plan from the detectors and prints
    it, spawning zero agent sessions and leaving the wiki byte-for-byte untouched (the wiki IS the
    database)."""
    from citadel import curate

    agent = fake_agent()
    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/alice.md", "raw/notes.md", type_="Person", title="Alice")
    before = (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8")

    report = curate.curate(dry_run=True)
    assert agent.count == 0  # no session on a dry run
    assert "concepts/alice.md" in _plan_pages(report.plan)
    assert (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8") == before


def test_limit_caps_the_recomputed_plan(tmp_citadel, seed_page):
    """--limit N takes only the first N clusters of the (deterministically ordered) plan."""
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    for slug in ("a", "b", "c"):
        _seed_cited(seed_page, f"concepts/{slug}.md", "raw/notes.md", type_="Person", title=slug.upper())

    assert len(curate.build_plan().items) >= 3
    assert len(curate.build_plan(limit=2).items) == 2


def test_stale_rules_selects_only_stale_stamped_sources_pages(tmp_citadel, seed_page):
    """--stale-rules narrows the plan to pages whose source was ingested under an older rules hash;
    a page whose source carries the CURRENT hash is excluded even if other detectors would flag it."""
    from citadel import curate

    (tmp_citadel.raw / "old.md").write_text("body\n", encoding="utf-8")
    (tmp_citadel.raw / "new.md").write_text("body\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/old.md", "raw/old.md", title="Old")
    _seed_cited(seed_page, "concepts/new.md", "raw/new.md", title="New")
    _track("raw/old.md", manifest.file_sha256(tmp_citadel.raw / "old.md"), "0000oldrules")
    _track("raw/new.md", manifest.file_sha256(tmp_citadel.raw / "new.md"), config.rules_version())

    pages = _plan_pages(curate.build_plan(stale_rules=True))
    assert "concepts/old.md" in pages
    assert "concepts/new.md" not in pages


# --- the cluster session: staging diff decides NOOP / applied / failed (one _SourceJob) -----


def _seed_resort_cluster(tmp_citadel, seed_page):
    """A single deterministically-flagged cluster: a Person page mis-filed under concepts/."""
    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    _seed_cited(seed_page, "concepts/alice.md", "raw/notes.md", type_="Person", title="Alice")


def test_cluster_applied_when_agent_edits_and_page_validates(tmp_citadel, seed_page, fake_agent):
    """A curate session that makes a clean, validated edit promotes onto the live wiki — the
    staging diff-by-hash is the SINGLE result arbiter (a non-empty, clean diff = applied)."""
    from citadel import curate

    _seed_resort_cluster(tmp_citadel, seed_page)
    fake_agent(
        pages={
            "concepts/alice.md": (
                {"type": "Person", "title": "Alice", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
                "Improved sourced fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n",
            )
        }
    )

    report = curate.curate()
    assert "concepts/alice.md" in report.applied
    assert "Improved sourced fact." in (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8")


def test_cluster_noop_when_agent_makes_no_edits(tmp_citadel, seed_page, fake_agent):
    """An agent that decides the findings do not hold up makes no edits; the empty staging diff is
    a NOOP — the wiki is unchanged and nothing is recorded as a failure."""
    from citadel import curate

    _seed_resort_cluster(tmp_citadel, seed_page)
    before = (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8")
    fake_agent(pages={})  # writes nothing into the staging copy

    report = curate.curate()
    assert "concepts/alice.md" in report.noop
    assert (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8") == before
    assert "concepts/alice.md" not in report.failed


def test_cluster_failed_validate_reverts_and_records_failure(tmp_citadel, seed_page, fake_agent):
    """A curate session whose edit fails the check gate promotes NOTHING — the live wiki is left
    exactly as it was (revert-and-stop) and the cluster is recorded in the failures catalog."""
    from citadel import curate, failures

    _seed_resort_cluster(tmp_citadel, seed_page)
    before = (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8")
    fake_agent(pages={"concepts/alice.md": "garbage with no frontmatter and no citations"})

    report = curate.curate()
    assert "concepts/alice.md" in report.failed
    assert (tmp_citadel.wiki / "concepts/alice.md").read_text(encoding="utf-8") == before  # untouched
    stuck = failures.load()
    assert "concepts/alice.md" in stuck
    assert stuck["concepts/alice.md"].get("attempts", 0) >= 1


def test_failed_cluster_is_attempt_capped_across_runs(tmp_citadel, seed_page, fake_agent):
    """A failing curate cluster is never auto-retried: its failures-catalog ``attempts`` counter
    increments per run and, once it reaches the cap (default 2), later runs SKIP the cluster
    (no further agent session) until an explicit re-try."""
    from citadel import curate, failures

    _seed_resort_cluster(tmp_citadel, seed_page)
    agent = fake_agent(pages={"concepts/alice.md": "still garbage"})

    curate.curate()  # attempt 1
    assert agent.count == 1
    curate.curate()  # attempt 2 -> reaches the cap
    assert agent.count == 2
    assert failures.load()["concepts/alice.md"]["attempts"] == 2
    curate.curate()  # capped: skipped, no new session
    assert agent.count == 2


# --- transparency side-effects: log.md edit summary + --diff report --------------------------


def test_applied_cluster_appends_edit_summary_to_log(tmp_citadel, seed_page, fake_agent):
    from citadel import curate

    _seed_resort_cluster(tmp_citadel, seed_page)
    fake_agent(
        pages={
            "concepts/alice.md": (
                {"type": "Person", "title": "Alice", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
                "Improved sourced fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n",
            )
        }
    )

    curate.curate()
    log_text = config.LOG_PATH.read_text(encoding="utf-8")
    assert "curate" in log_text.lower()
    assert "concepts/alice.md" in log_text


def test_diff_report_is_written(tmp_citadel, seed_page, fake_agent):
    from citadel import curate

    _seed_resort_cluster(tmp_citadel, seed_page)
    fake_agent(
        pages={
            "concepts/alice.md": (
                {"type": "Person", "title": "Alice", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
                "Improved sourced fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n",
            )
        }
    )
    report_path = tmp_citadel.root / "curate-diff.md"

    curate.curate(diff=str(report_path))
    assert report_path.is_file()
    assert "concepts/alice.md" in report_path.read_text(encoding="utf-8")


# --- citadel status (Z11): per-source table from the manifest + failures catalog ------------


def test_status_reports_ingested_and_failed_sources(tmp_citadel, seed_page):
    """`citadel status` answers 'what state is my corpus in' — the ingested sources (with model +
    rules_version stamp) and the failed ones (reason + attempts), read from the manifest + the
    failures catalog."""
    from citadel import failures, status

    (tmp_citadel.raw / "good.md").write_text("body\n", encoding="utf-8")
    _track("raw/good.md", manifest.file_sha256(tmp_citadel.raw / "good.md"), config.rules_version())
    stuck: dict[str, dict] = {}
    failures.record(stuck, "raw/scan.tiff", failures.UNREADABLE, "no extractable text", "claude:sonnet")
    failures.save(stuck)

    report = status.build_status()
    text = report.render()
    assert "raw/good.md" in text  # the ingested side
    assert "raw/scan.tiff" in text and "unreadable" in text  # the failed side
    assert report.ingested and report.failed  # structured collections, not just prose


# --- MCP <-> CLI parity (Z11): read/index/sources CLI wrappers + wiki_lint tool --------------


def test_every_mcp_tool_has_a_cli_counterpart():
    """Full MCP<->CLI parity: every MCP tool has a CLI equivalent so an AI without MCP access can
    do everything through the CLI. lint/view stay CLI-only by design; wiki_lint closes the gap
    from the MCP side."""
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "wiki_lint" in tools  # the MCP side of the parity

    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    commands = set(sub.choices)
    mcp_to_cli = {
        "wiki_search": "search",
        "wiki_read": "read",
        "wiki_index": "index",
        "wiki_sources": "sources",
        "wiki_tags": "tags",
        "wiki_validate": "check",
        "wiki_ingest": "ingest",
        "wiki_lint": "lint",
    }
    for tool, subcommand in mcp_to_cli.items():
        assert subcommand in commands, f"MCP {tool} has no CLI counterpart {subcommand!r}"


def test_wiki_lint_tool_never_raises(tmp_citadel, monkeypatch):
    """The new wiki_lint MCP tool honors the server's never-raise contract: an internal failure
    comes back as a clear error STRING, not an exception, so the server stays up."""
    wiki_lint = server.wiki_lint  # the never-raise MCP tool

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(lint, "lint", boom)
    out = wiki_lint()
    assert isinstance(out, str) and out.lower().startswith("error")


# --- Z6 locator lint checks for text-bearing raw sources ------------------------------------


def test_lint_flags_out_of_range_line_locator(tmp_citadel, seed_page):
    """A `lines A-B` locator pointing past the end of its (immutable) text source is a lint
    warning — the deterministic half of Z6 provenance precision."""
    (tmp_citadel.raw / "notes.md").write_text("line one\nline two\nline three\n", encoding="utf-8")  # 3 lines
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md), lines 40-52 - out of range\n",
    )

    report = lint.lint()
    issues = report.locator_issues  # new LintReport field -> AttributeError until Z6 lands
    assert any("concepts/topic.md" == rel for rel, _detail in issues)


def test_lint_flags_missing_heading_locator(tmp_citadel, seed_page):
    """A `§ Heading` locator naming a heading that does not exist in its text source is a lint
    warning."""
    (tmp_citadel.raw / "spec.md").write_text("# Real Heading\n\nprose\n", encoding="utf-8")
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["t"], "resource": "raw/spec.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/spec.md](../../raw/spec.md), § Nonexistent Heading - x\n",
    )

    report = lint.lint()
    issues = report.locator_issues  # AttributeError until Z6 lands
    assert any("concepts/topic.md" == rel for rel, _detail in issues)
