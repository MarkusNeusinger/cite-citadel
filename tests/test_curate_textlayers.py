"""#161 (offline): curate hands a session the text layer of each cited PDF and refuses a cluster
that downgrades verifiable `lines A-B` locators into a PDF to `p. N`."""

from __future__ import annotations

from pathlib import Path

import pytest

from citadel import config, curate, grammar, manifest, pdftext


def _pdf(tmp_citadel, name: str) -> str:
    path = tmp_citadel.raw / name
    path.write_bytes(b"%PDF-1.4\n" + name.encode() + b"\n")
    m = manifest.load()
    m[f"raw/{name}"] = manifest.make_entry(manifest.file_sha256(path), "claude:x", config.rules_version())
    manifest.save(m)
    return f"raw/{name}"


def _cite(seed_page, rel_path: str, keys: list[str], locator: str = "lines 1-1", links: str = "") -> None:
    defs = "\n".join(f"[^s{i}]: [{k}](../../{k}), {locator} - d" for i, k in enumerate(keys, 1))
    marks = "".join(f"Fact {i}.[^s{i}] " for i in range(1, len(keys) + 1))
    seed_page(
        rel_path,
        {"type": "Concept", "title": Path(rel_path).stem, "description": "d", "tags": ["t"], "resource": keys[0]},
        f"{marks}{links}\n\n## Sources\n\n{defs}\n",
    )


@pytest.fixture
def layers(monkeypatch):
    calls: list[str] = []

    def text_for(src, sha=None):
        calls.append(Path(src).name)
        return f"[p. 1]\ntext of {Path(src).name}\n"

    monkeypatch.setattr(pdftext, "text_for", text_for)
    return calls


def _findings_seen(fake_agent):
    seen: list[str] = []

    def effect(rel_key, kind="curate", read_path=None, **kw):
        text = Path(config.source_path_for_key(read_path)).read_text(encoding="utf-8")
        seen.append(text)
        for line in text.splitlines():
            if " -> " in line and line.startswith("- raw/"):
                copy = Path(config.source_path_for_key(line.split(" -> ", 1)[1]))
                assert copy.is_file() and str(copy).startswith(str(Path(config.source_path_for_key(read_path)).parent))

    fake_agent(side_effect=effect)
    return seen


def test_the_findings_hand_over_a_copy_of_each_text_layer(tmp_citadel, seed_page, fake_agent, layers, monkeypatch):
    key = _pdf(tmp_citadel, "a.pdf")
    _cite(seed_page, "concepts/x.md", [key])
    seen = _findings_seen(fake_agent)
    curate.curate(["concepts/x.md"])
    assert "- PDF mode: text" in seen[0]
    assert "## Text layers of cited PDFs" in seen[0] and "- raw/a.pdf -> " in seen[0]
    monkeypatch.setattr(config, "PDF_MODE", "images")
    seen.clear()
    curate.curate(["concepts/x.md"])
    assert "- PDF mode: images" in seen[0]


def test_a_neighbors_pdf_is_listed_and_the_cap_holds(tmp_citadel, seed_page, fake_agent, layers):
    keys = [_pdf(tmp_citadel, f"p{i:02d}.pdf") for i in range(12)]
    other = _pdf(tmp_citadel, "neighbor.pdf")
    _cite(seed_page, "concepts/n.md", [other])
    _cite(seed_page, "concepts/x.md", keys, links="See [N](n.md).")
    seen = _findings_seen(fake_agent)
    curate.curate(["concepts/x.md"])
    listed = [line for line in seen[0].splitlines() if line.startswith("- raw/") and " -> " in line]
    assert len(listed) == 10 and "3 more cited PDFs" in seen[0]


@pytest.mark.parametrize("case", ["none", "knob_off", "not_pdf", "changed", "oserror"])
def test_nothing_listed_and_the_cluster_still_runs(tmp_citadel, seed_page, fake_agent, monkeypatch, case):
    key = _pdf(tmp_citadel, "a.pdf")
    monkeypatch.setattr(pdftext, "text_for", lambda src, sha=None: None if case == "none" else "[p. 1]\nt\n")
    if case == "knob_off":
        monkeypatch.setattr(config, "PDF_TEXT", "off", raising=False)
    if case == "not_pdf":
        (tmp_citadel.raw / "a.pdf").write_text("plain text\n", encoding="utf-8")
    if case == "changed":
        (tmp_citadel.raw / "a.pdf").write_bytes(b"%PDF-1.4\nchanged\n")
    if case == "oserror":
        real = Path.write_bytes

        def boom(self, data):
            if "textlayers" in str(self):
                raise OSError("disk full")
            return real(self, data)

        monkeypatch.setattr(Path, "write_bytes", boom)
    _cite(seed_page, "concepts/x.md", [key])
    seen = _findings_seen(fake_agent)
    curate.curate(["concepts/x.md"])
    assert len(seen) == 1 and "## Text layers of cited PDFs" not in seen[0]


def test_a_cluster_citing_no_pdf_gets_todays_findings(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("a\n", encoding="utf-8")
    _cite(seed_page, "concepts/x.md", ["raw/a.md"])
    from citadel import store

    page = store.read_page("concepts/x.md")
    item = curate.PlanItem(page="concepts/x.md", reasons=["orphan"])
    plain = curate._render_findings(item, page, {})
    read_path, tmpdir = curate._write_findings(
        item, page, {}, pages_by_path={page.rel_path: page}, manifest_dict={}, memo=curate._TextLayerMemo()
    )
    try:
        assert Path(config.source_path_for_key(read_path)).read_text(encoding="utf-8") == plain
    finally:
        import shutil

        shutil.rmtree(tmpdir)


def test_two_clusters_citing_one_pdf_extract_it_once(tmp_citadel, seed_page, fake_agent, layers):
    key = _pdf(tmp_citadel, "a.pdf")
    _cite(seed_page, "concepts/x.md", [key])
    _cite(seed_page, "concepts/y.md", [key])
    _findings_seen(fake_agent)
    curate.curate(["concepts/x.md", "concepts/y.md"])
    assert layers == ["a.pdf"]


def test_the_copies_are_gone_after_success_and_failure(tmp_citadel, seed_page, fake_agent, layers):
    key = _pdf(tmp_citadel, "a.pdf")
    _cite(seed_page, "concepts/x.md", [key])
    dirs: list[Path] = []

    def effect(rel_key, kind="curate", read_path=None, **kw):
        dirs.append(Path(config.source_path_for_key(read_path)).parent)
        raise RuntimeError("fail")

    fake_agent(side_effect=effect)
    curate.curate(["concepts/x.md"], force=True)
    assert dirs and not dirs[0].exists()


# --- the downgrade guard -----------------------------------------------------------------------


def test_rewriting_lines_to_p_fails_the_cluster(tmp_citadel, seed_page, fake_agent, layers):
    key = _pdf(tmp_citadel, "a.pdf")
    _cite(seed_page, "concepts/x.md", [key], locator="lines 4-6")
    live = (tmp_citadel.wiki / "concepts" / "x.md").read_bytes()

    def effect(rel_key, **kw):
        path = config.wiki_dir() / "concepts" / "x.md"
        path.write_text(path.read_text(encoding="utf-8").replace("lines 4-6", "p. 1"), encoding="utf-8")

    fake_agent(side_effect=effect)
    report = curate.curate(["concepts/x.md"])
    assert report.failed == ["concepts/x.md"] and "raw/a.pdf" in report.failed_details["concepts/x.md"]
    assert (tmp_citadel.wiki / "concepts" / "x.md").read_bytes() == live


def test_legitimate_edits_are_not_flagged(tmp_citadel, seed_page):
    key = _pdf(tmp_citadel, "a.pdf")
    _cite(seed_page, "concepts/x.md", [key], locator="lines 4-6")
    from citadel import store

    base = curate._pdf_locator_counts(store.load())
    # A dropped fact lowers lines only; a split copying a p. definition raises page only.
    assert not curate._no_locator_downgrade({**base, key: (base[key][0] + 1, base[key][1])})()
    # A PDF that only ever had p. N locators is never guarded.
    assert not curate._no_locator_downgrade({"raw/b.pdf": (0, 2)})()


@pytest.mark.parametrize(
    ("tail", "expected"),
    [("p. 12", True), ("p.12", True), ("pp. 3-5", True), ("lines 4-6", False), ("line 4", False), ("§ Intro", False)],
)
def test_is_page_locator(tail, expected):
    assert grammar.is_page_locator(tail) is expected
