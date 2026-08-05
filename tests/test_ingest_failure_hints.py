"""Per-failure guidance (offline): when a failure leaves a DEFECT in the live wiki rather than
just leaving work undone, the run report has to say what to do about it.

The generic errors footer tells the user the source is retried next run. For a failed deletion
cleanup that is not the whole story: the pages it named keep citing a source file that no longer
exists, and no retry of that source repairs the wiki if the agent is what is broken. Without a
pointer to `citadel lint` / `citadel curate`, a dangling `[^sN]` sits in the wiki unnoticed —
which is exactly how the incident behind this machinery played out.

``llm.run_ingest_session`` is replaced by ``fake_agent`` — no CLI is ever spawned.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, ingest, manifest, okf


def _seed_vanished_source(seed_page) -> None:
    """One page citing a tracked source that is gone from disk, so a full run plans a cleanup."""
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/kept.md"},
        "A true fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/kept.md](../../raw/kept.md) - kept\n"
        "[^s2]: [raw/vanished.md](../../raw/vanished.md) - vanished\n",
    )
    tracked = manifest.load()
    tracked["raw/vanished.md"] = manifest.make_entry("dd" * 32, None)
    manifest.save(tracked)


def test_failed_cleanup_names_the_tools_that_fix_the_leftover(tmp_citadel, fake_agent, seed_page):
    """THE POINT. A cleanup that changes nothing fails its post-condition and leaves a dangling
    citation behind. The report must name the page AND what repairs it — `citadel lint` to see it,
    `citadel curate` to fix it — not just offer a retry that cannot help while the agent is dead."""
    cit = tmp_citadel
    _seed_vanished_source(seed_page)
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")

    fake_agent()  # the dead agent: the cleanup session does nothing at all
    report = ingest.ingest()

    assert any("still cited by" in e for e in report.errors)
    rendered = report.render()
    assert "concepts/topic.md" in rendered, "the affected page must be named"
    assert "citadel lint" in rendered
    assert "citadel curate" in rendered
    assert "no longer exists" in rendered


def test_no_hint_when_the_cleanup_succeeds(tmp_citadel, fake_agent, seed_page):
    """The hint is failure-scoped. A cleanup that does its job leaves no defect, so nothing about
    lint/curate belongs in that run's report."""
    cit = tmp_citadel
    _seed_vanished_source(seed_page)
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")

    def strip_it(rel_key, kind="ingest", **kwargs):
        if kind != "delete":
            return
        page = Path(config.wiki_dir()) / "concepts/topic.md"
        frontmatter, body = okf.parse(page.read_text(encoding="utf-8"))
        body = body.replace("[^s2]: [raw/vanished.md](../../raw/vanished.md) - vanished\n", "")
        page.write_text(okf.dump(frontmatter, body), encoding="utf-8")

    fake_agent(side_effect=strip_it)
    report = ingest.ingest()

    assert report.sources_deleted == ["raw/vanished.md"]
    assert report.failure_hints == []
    assert "citadel curate" not in report.render()


def test_an_ordinary_source_failure_gets_no_cleanup_hint(tmp_citadel, fake_agent):
    """A source whose session raised is rolled back — the live wiki is untouched, so there is
    nothing to repair and the generic retry advice really is the whole story."""
    cit = tmp_citadel
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")

    fake_agent(error=RuntimeError("session boom"))
    report = ingest.ingest()

    assert report.errors
    assert report.failure_hints == []
    rendered = report.render()
    assert "citadel ingest --retry" in rendered  # the generic footer still applies
    assert "citadel curate" not in rendered


def test_the_hint_appears_once_for_several_failed_cleanups(tmp_citadel, fake_agent, seed_page):
    """Two vanished sources, two failed cleanups, one hint — it is advice about a situation, not a
    per-source error line, and repeating it would bury the errors it sits under."""
    cit = tmp_citadel
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    for name in ("gone-a", "gone-b"):
        seed_page(
            f"concepts/{name}.md",
            {"type": "Concept", "title": name, "description": "d", "tags": ["x"], "resource": "raw/kept.md"},
            f"Fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/{name}.md](../../raw/{name}.md) - g\n",
        )
    tracked = manifest.load()
    for i, name in enumerate(("gone-a", "gone-b")):
        tracked[f"raw/{name}.md"] = manifest.make_entry(f"{i}{i}" * 32, None)
    manifest.save(tracked)

    fake_agent()
    report = ingest.ingest()

    assert len([e for e in report.errors if "still cited by" in e]) == 2
    assert len(report.failure_hints) == 1
    assert report.render().count("citadel curate") == 1
