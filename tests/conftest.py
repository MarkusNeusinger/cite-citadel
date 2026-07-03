"""Shared fixtures for the citadel test suite (offline — no CLI, no network, ever).

Every test that touches the filesystem is redirected into ``tmp_path`` by monkeypatching the
``config.*`` attributes (the codebase reads ``config`` at call time, so patching the module
attributes is the single supported seam). The agent bridge is replaced per-test with a
:class:`FakeAgent` installed over ``llm.run_ingest_session`` — no test spawns a real CLI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from citadel import config, llm, manifest, okf, repo, store


# --- layout wiring -----------------------------------------------------------------------


# Prompt-size budget for the paths-only argv guard (WinError 206). The real Windows limit is
# 32,767 chars for the WHOLE CreateProcess command line; the guard only has to prove the prompt
# stays paths-only (never embeds file content). 8000 leaves ~4x margin while absorbing long CI
# runner tmp paths and the absolute packaged-rules paths.
PROMPT_CHAR_BUDGET = 8000

# The REAL packaged rules tree (citadel/rules/ in this checkout / site-packages), captured at
# import time — BEFORE any fixture monkeypatches config.PACKAGED_RULES_DIR onto a stub tree.
# Content tests (what the rulebook must keep teaching) read from here.
REAL_RULES_DIR = config.PACKAGED_RULES_DIR


@pytest.fixture(autouse=True)
def _stable_workspace_found(monkeypatch):
    """Pin ``config.WORKSPACE_FOUND`` to True for EVERY test, so the suite behaves identically
    no matter which CWD pytest was launched from (workspace discovery runs at import time and
    would otherwise leak the developer's CWD into ``cli.main``'s fail-loud guard). A test
    exercising the guard overrides this with ``monkeypatch.setattr(config, "WORKSPACE_FOUND",
    False)``."""
    monkeypatch.setattr(config, "WORKSPACE_FOUND", True)


@dataclass(frozen=True)
class CitadelTmp:
    """Handle onto a temp citadel layout that has been wired into ``config``.

    THIN SEAM — depend only on this interface. Tests must reach the temp layout exclusively
    through these attributes (``cit.wiki / "concepts/x.md"``, ``cit.raw / "notes.md"``, ...),
    never by re-deriving paths from ``tmp_path`` or by assuming which ``config.*`` attributes
    were patched: a later PR swaps the root-resolution internals (workspace discovery), and
    only this interface is guaranteed to survive that swap.
    """

    root: Path  # the (fake) workspace root -> config.WORKSPACE_ROOT
    wiki: Path  # config.WIKI_DIR
    raw: Path  # config.RAW_DIR
    docs: Path  # config.DOCS_DIR
    index_path: Path  # config.INDEX_PATH
    sources_index_path: Path  # config.SOURCES_INDEX_PATH
    log_path: Path  # config.LOG_PATH
    manifest_path: Path  # config.MANIFEST_PATH
    failures_path: Path  # config.FAILURES_PATH
    packaged_rules: Path  # config.PACKAGED_RULES_DIR (a stub tree at <root>/citadel/rules)

    def read_manifest(self) -> dict:
        """The manifest's flat ``{source key: entry}`` dict, read from THIS layout's live
        manifest file — the seam tests assert source entries through, instead of hand-unwrapping
        the on-disk shape (which tests/test_workspace.py pins deliberately).

        Reads ``self.manifest_path`` directly rather than calling ``manifest.load()``: the
        dataclass pins the LIVE path, so the read stays correct even from a hook that runs while
        ingest has ``config`` repointed at its per-source staging copy. Unwraps the format-2
        ``{"meta", "sources"}`` envelope (a legacy flat mapping reads as-is) and returns {} when
        no manifest exists yet."""
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        sources = data.get("sources") if isinstance(data, dict) else None
        return sources if isinstance(sources, dict) else data


@pytest.fixture
def make_citadel(tmp_path: Path, monkeypatch) -> Callable[..., CitadelTmp]:
    """Factory behind ``tmp_citadel``/``tmp_citadel_external`` for tests that need a custom
    layout (nested wiki dir, repo root in a subtree, ...). Wires the UNION of every config
    attribute the suite's old per-file helpers patched, so no test leaks onto the real repo."""

    def _make(
        *, root: Path | None = None, wiki: Path | None = None, raw: Path | None = None, docs: Path | None = None
    ) -> CitadelTmp:
        root = root if root is not None else tmp_path
        wiki = wiki if wiki is not None else root / "wiki"
        raw = raw if raw is not None else root / "raw"
        docs = docs if docs is not None else root / "docs"
        for d in (root, wiki, raw, docs):
            d.mkdir(parents=True, exist_ok=True)

        # A minimal STUB packaged-rules tree at <root>/citadel/rules — mirroring the dev-checkout
        # shape — so prompt builders resolve short, workspace-relative rule paths, _external_dirs
        # stays empty for the default layout, and nothing depends on where the REAL checkout lives
        # on disk. llm is always faked in ingest tests; these files only need to exist (and hash
        # stably for config.rules_version). Tests about the real rulebook's CONTENT read the real
        # packaged tree explicitly (it is captured before this patch, e.g. in test_llm.py).
        packaged_rules = root / "citadel" / "rules"
        for rel in (
            "schema.md",
            "core.md",
            "tasks/ingest.md",
            "tasks/reconcile.md",
            "tasks/delete.md",
            "tasks/curate.md",
            "formats/repo.md",
            "formats/image.md",
            "formats/pdf.md",
            "formats/office.md",
            "genres/prose.md",
        ):
            stub = packaged_rules / rel
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text(f"# {rel} (test stub)\n", encoding="utf-8")

        cit = CitadelTmp(
            root=root,
            wiki=wiki,
            raw=raw,
            docs=docs,
            index_path=wiki / "index.md",
            sources_index_path=wiki / "sources" / "index.md",
            log_path=wiki / "log.md",
            manifest_path=wiki / ".citadel_ingested.json",
            failures_path=wiki / ".citadel_failures.json",
            packaged_rules=packaged_rules,
        )
        # raising=True (the default): every one of these attributes exists in config today, so
        # a PR that renames the config internals makes this seam fail LOUD instead of silently
        # patching a dead attribute while the code reads the real (repo-local) one.
        monkeypatch.setattr(config, "WORKSPACE_ROOT", cit.root)
        monkeypatch.setattr(config, "WIKI_DIR", cit.wiki)
        monkeypatch.setattr(config, "RAW_DIR", cit.raw)
        # The multi-root walk list mirrors the single-root default ([RAW_DIR]); multi-root tests
        # re-patch it with their extra roots.
        monkeypatch.setattr(config, "RAW_DIRS", [cit.raw])
        monkeypatch.setattr(config, "DOCS_DIR", cit.docs)
        monkeypatch.setattr(config, "PACKAGED_RULES_DIR", cit.packaged_rules)
        monkeypatch.setattr(config, "INDEX_PATH", cit.index_path)
        monkeypatch.setattr(config, "SOURCES_INDEX_PATH", cit.sources_index_path)
        monkeypatch.setattr(config, "LOG_PATH", cit.log_path)
        monkeypatch.setattr(config, "MANIFEST_PATH", cit.manifest_path)
        monkeypatch.setattr(config, "FAILURES_PATH", cit.failures_path)
        return cit

    return _make


@pytest.fixture
def tmp_citadel(make_citadel) -> CitadelTmp:
    """The default in-repo layout: wiki/, raw/, docs/ directly under the temp repo root."""
    return make_citadel()


@pytest.fixture
def repo_wiki(tmp_citadel, monkeypatch) -> CitadelTmp:
    """``tmp_citadel`` with repo-source support forced ON (the environment could disable it)."""
    monkeypatch.setattr(config, "REPO_SUPPORT", True, raising=False)
    return tmp_citadel


def _make_repo(raw: Path, name: str, files: dict[str, str], marker: bool = True) -> Path:
    """Create a folder under raw/ with the given files; add the ``.citadelsource`` marker so it is
    treated as one repo source without needing git."""
    root = raw / name
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if marker:
        (root / repo.MARKER).write_text("", encoding="utf-8")
    return root


@pytest.fixture
def make_repo() -> Callable[..., Path]:
    """Build a marker-based (hermetic, no git binary) repo source under any directory —
    ``make_repo(raw, "svc", {"app.py": "x\\n"})`` — returning the repo root."""
    return _make_repo


@pytest.fixture
def tmp_citadel_external(make_citadel, tmp_path: Path) -> CitadelTmp:
    """The out-of-repo layout: the repo checkout on one subtree; wiki/ and raw/ on a SEPARATE
    'net' subtree (a shared parent, as a mounted network drive would have); docs/ stays inside
    the repo. Models ``CITADEL_WIKI_DIR=T:\\team-wiki\\wiki`` next to a normal checkout."""
    net = tmp_path / "net"  # stands in for T:\team-wiki
    return make_citadel(root=tmp_path / "repo", wiki=net / "wiki", raw=net / "raw")


# --- seeding pages -----------------------------------------------------------------------


@pytest.fixture
def seed_page() -> Callable[..., Path]:
    """Write a canonical OKF page directly under the CONFIGURED wiki (bypassing ingest).

    Reads ``config.WIKI_DIR`` at call time, so it composes with any layout fixture
    (``tmp_citadel``, ``tmp_citadel_external``, or a custom ``make_citadel`` layout).
    """

    def _seed(rel_path: str, frontmatter: dict, body: str = "Body.\n") -> Path:
        target = Path(config.WIKI_DIR) / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(okf.dump(frontmatter, body), encoding="utf-8")
        return target

    return _seed


def _cite_page(rel_path: str, rel_key: str, body_fact: str) -> None:
    """Write a minimal valid OKF page that cites ``rel_key`` once (for use inside fake sessions).
    A workspace-relative key is cited with a relative link; an absolute (out-of-workspace) key by
    its absolute posix path — the Z3 cross-root citation form.

    Absoluteness is decided with the NATIVE ``Path`` flavor (the same discipline as
    ``config.source_path_for_key``), never ``PurePosixPath``: keys are produced by
    ``config.rel_or_abs_posix`` on the platform under test, and a Windows drive-letter key
    (``C:/Users/...``) is NOT posix-absolute — ``PurePosixPath("C:/x").is_absolute()`` is False —
    which would emit a broken ``../../C:/...`` link and fail every fake session for an
    out-of-workspace source on Windows."""
    link = rel_key if Path(rel_key).is_absolute() else f"../../{rel_key}"
    target = config.WIKI_DIR / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        okf.dump(
            {"type": "Note", "title": "Fact", "description": "d", "tags": ["t"], "resource": rel_key},
            f"{body_fact}[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}]({link}) - src (ingested 2026-06-21)\n",
        ),
        encoding="utf-8",
    )


@pytest.fixture
def cite_page() -> Callable[[str, str, str], None]:
    """``seed_page``'s little sibling for fake-session bodies: ``cite_page(rel_path, rel_key,
    fact)`` writes one valid page whose single fact cites ``rel_key``. Reads ``config.WIKI_DIR``
    at call time, so inside a session it lands in ingest's per-source staging copy."""
    return _cite_page


@pytest.fixture
def seed_cited_deleted_source(seed_page) -> Callable[[], None]:
    """Seed the canonical VANISHED-source setup shared across suites: one wiki page
    (``concepts/topic.md``) citing ``raw/gone.md`` plus a manifest entry for it, with NO file on
    disk — so the next full run detects the deletion and must run a ``kind="delete"`` cleanup
    session. Updates the manifest in place (load-save), composing with already-tracked sources."""

    def _seed() -> None:
        seed_page(
            "concepts/topic.md",
            {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
        )
        tracked = manifest.load()
        tracked["raw/gone.md"] = manifest.make_entry("dd" * 32, None)
        manifest.save(tracked)

    return _seed


def delete_citing_pages(rel_key: str) -> None:
    """The ``kind="delete"`` fake-session idiom shared across suites: remove every page citing
    ``rel_key`` from the CONFIGURED wiki — ingest's per-source staging copy at call time, exactly
    like the real agent's file edits — enough to satisfy the delete post-condition."""
    for rel in store.find_raw_references(rel_key):
        (Path(config.WIKI_DIR) / rel).unlink(missing_ok=True)


def _make_pptx(path: Path, slides: list[list[str]]) -> None:
    """Write a minimal real ``.pptx`` (a ZIP of slide XML) at ``path``; ``slides`` is a list of
    slides, each a list of paragraph strings. An empty slide ([]) carries no text."""
    import zipfile

    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    with zipfile.ZipFile(path, "w") as z:
        for i, paras in enumerate(slides, 1):
            runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
            z.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<?xml version="1.0"?><p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree>'
                f"<p:sp><p:txBody>{runs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
            )


@pytest.fixture
def make_pptx() -> Callable[[Path, list[list[str]]], None]:
    """Materialize a tiny real PowerPoint file for Office-extraction tests:
    ``make_pptx(raw / "deck.pptx", [["para", ...], ...])`` (one inner list per slide)."""
    return _make_pptx


@pytest.fixture
def transformer_page() -> dict:
    """The canonical one-page agent output (a Concept citing raw/notes.md) that many ingest tests
    share — pass it straight to ``fake_agent`` to reproduce one deterministic ingest session."""
    return {
        "concepts/transformer.md": (
            {
                "type": "Concept",
                "title": "Transformer",
                "description": "self-attention model",
                "tags": ["ml"],
                "resource": "raw/notes.md",
            },
            "Transformers use self-attention.[^s1]\n\n"
            "## Sources\n\n"
            "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n",
        )
    }


# --- faking the agent session ------------------------------------------------------------


class FakeAgent:
    """Deterministic stand-in for ``llm.run_ingest_session`` — the single seam tests patch.

    The real agent has no return value: its file edits ARE the result. So the fake, per call:
      1. records ``(rel_key, kind)`` in ``self.calls`` (assert on ``calls``/``count``);
      2. raises ``error`` if given (a failed/timed-out session);
      3. writes ``pages`` into the configured wiki — ingest's per-source STAGING copy, since
         ``config.WIKI_DIR`` is read at call time (``{rel_path: (frontmatter, body)}`` dumped
         via ``okf.dump``, or ``{rel_path: str}`` written verbatim);
      4. passes the original args through to ``side_effect`` for bespoke per-call behavior
         (e.g. deleting the pages that cite a removed source).
    """

    def __init__(
        self,
        pages: dict[str, Any] | None = None,
        *,
        error: BaseException | None = None,
        side_effect: Callable[..., None] | None = None,
    ) -> None:
        self.pages = dict(pages or {})
        self.error = error
        self.side_effect = side_effect
        self.calls: list[tuple[str, str]] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()

    def __call__(self, *args, **kwargs) -> None:
        rel_key = args[0] if args else kwargs.get("rel_key")
        kind = args[1] if len(args) > 1 else kwargs.get("kind", "ingest")
        self.calls.append((rel_key, kind))
        if self.error is not None:
            raise self.error
        for rel_path, content in self.pages.items():
            target = Path(config.WIKI_DIR) / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            text = content if isinstance(content, str) else okf.dump(*content)
            target.write_text(text, encoding="utf-8")
        if self.side_effect is not None:
            self.side_effect(*args, **kwargs)


@pytest.fixture
def fake_agent(monkeypatch) -> Callable[..., FakeAgent]:
    """Factory: build a :class:`FakeAgent`, install it as ``llm.run_ingest_session`` (the one
    place that would talk to an LLM), and return it for assertions."""

    def _install(
        pages: dict[str, Any] | None = None,
        *,
        error: BaseException | None = None,
        side_effect: Callable[..., None] | None = None,
    ) -> FakeAgent:
        agent = FakeAgent(pages, error=error, side_effect=side_effect)
        monkeypatch.setattr(llm, "run_ingest_session", agent, raising=False)
        return agent

    return _install


def errors_of(issues):
    """Filter validate issues down to severity=='error' (the strict-gate view)."""
    return [i for i in issues if i.severity == "error"]
