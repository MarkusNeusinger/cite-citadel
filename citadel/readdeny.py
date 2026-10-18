"""Per-path Read denies for claude agent sessions — enforcement of the corpus exclusions.

Discovery keeps excluded files (``CITADEL_IGNORE_PATTERNS`` user and built-in globs, files outside
``CITADEL_INCLUDE_PATTERNS``, files over ``CITADEL_MAX_SOURCE_BYTES``) out of the SOURCE list, but
an agent session can still open one on its own — a sidecar stored beside its source, a related-
source lookup. Uncited, such reading is invisible: excluded content shapes the prose and no
citation ever surfaces it. The run instruction says "never open these" for every backend; for
claude this module adds ENFORCEMENT: a per-session ``--settings`` file holding exactly
``{"permissions": {"deny": ["Read(//abs/path)", ...]}}``.

The entries come from the run's own discovery walk (never from re-translated globs — fnmatch and
gitignore semantics would drift, and size/allowlist exclusions are not globs at all): an ignored
directory, or a directory under which the walk admitted no file, becomes ONE ``Read(//dir/**)``
rule. Paths are absolute in claude's ``//`` form, spelled the child-friendly way
(:func:`config.native_form`). A session's own source, its prepared file, the wiki/staging dir, the
cache siblings, the rules dirs and ``docs/`` are never denied — a directory rule that would cover
one is expanded into its other entries (deny beats allow, so a carve-out is impossible).

Rules are capped at :data:`DENY_CAP` (directory rules first); what the cap leaves unenforced is
counted and reported, never silent. Per Anthropic's docs Read denies cover the Read/Grep/Glob tools,
the file commands claude recognizes in Bash and redirections — not interpreters, which is why the
shell itself is narrowed in :func:`llm._build_invocation`.

State is per RUN (``install``/``clear``, called where ingest and curate start), shared by every
``--jobs`` worker of that run; nothing is persisted.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path, PurePath

from . import config


# The most deny rules one session's settings file carries. Directory rules come first, so the cap
# drops individual files before whole folders.
DENY_CAP = 2000

# How many entries are examined when a directory rule must be expanded around a protected path
# (an explicitly named source inside an ignored folder) — the expansion walks only the branch that
# leads to the protected path, so this bounds one pathological folder, not normal operation.
_EXPAND_CAP = 5000

_LOCK = threading.Lock()
_RUN_ENTRIES: list[tuple[Path, bool]] | None = None
_UNENFORCED = 0


def entries_from_walk(walk) -> list[tuple[Path, bool]]:
    """The ``(path, is_dir)`` deny entries one discovery walk (``ingest_scan._Walk``) yields: every
    ignored entry as walked (a directory whole), plus the allowlist/size exclusions — each
    collapsed to its HIGHEST ancestor below the raw root under which the walk admitted no file, so a
    folder of 300 excluded PDFs is one rule instead of 300. Deterministic order: directories first,
    then files, each sorted."""
    admitted: set[str] = set()
    for path, _st in walk.files:
        for parent in Path(path).parents:
            admitted.add(str(parent))
    entries: dict[str, tuple[Path, bool]] = {}
    for path, is_dir in walk.ignored:
        entries[str(path)] = (Path(path), bool(is_dir))
    for path in [*walk.not_included, *(p for p, _size in walk.oversized)]:
        path = Path(path)
        root = config.root_covering(path)
        best: tuple[Path, bool] = (path, False)
        if root is not None:
            for parent in path.parents:
                if not _within(str(parent), str(root)) or _within(str(root), str(parent)):
                    break
                if str(parent) in admitted:
                    break
                best = (parent, True)
        entries[str(best[0])] = best
    # Drop entries already covered by a directory entry.
    dirs = sorted({str(p) for p, d in entries.values() if d}, key=len)
    kept: list[tuple[Path, bool]] = []
    for key, (path, is_dir) in entries.items():
        if any(key != d and _within(key, d) for d in dirs):
            continue
        kept.append((path, is_dir))
    kept.sort(key=lambda e: (not e[1], str(e[0])))
    return kept


def install(entries: list[tuple[Path, bool]] | None) -> None:
    """Set this run's deny entries (None/empty: nothing enforced). Called once per run."""
    global _RUN_ENTRIES, _UNENFORCED
    with _LOCK:
        _RUN_ENTRIES = list(entries) if entries else None
        _UNENFORCED = 0


def clear() -> None:
    install(None)


def note_unenforced(count: int) -> None:
    """Record that one session's cap left ``count`` entries unenforced (the run keeps the max)."""
    global _UNENFORCED
    with _LOCK:
        _UNENFORCED = max(_UNENFORCED, count)


def unenforced() -> int:
    with _LOCK:
        return _UNENFORCED


def install_from_discovery(walk=None) -> None:
    """Install this run's deny entries from a FULL discovery walk (``walk`` when the caller already
    holds one over every root, else a fresh stat-only one) — claude only, the one backend whose
    settings can enforce them. Best-effort: a walk failure installs nothing."""
    from . import ingest_scan, llm  # call-time: both import far more than this module needs

    if llm.resolve_cli_name(config.LLM_CLI) != "claude":
        clear()
        return
    try:
        install(entries_from_walk(walk if walk is not None else ingest_scan._discover_walk(None)))
    except OSError:
        clear()


def current() -> list[tuple[Path, bool]]:
    with _LOCK:
        return list(_RUN_ENTRIES or [])


def _within(path: str, base: str) -> bool:
    p, b = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(base))
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def rule_for(path: Path | str, is_dir: bool) -> str:
    """claude's absolute Read rule for ``path``: ``Read(//abs/path)`` (``/**`` for a directory). A
    Windows drive path ``T:\\x`` is written ``//t/x``; the child-friendly spelling is used."""
    text = PurePath(config.native_form(Path(path))).as_posix()
    if len(text) >= 2 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    elif text.startswith("//"):
        text = text[1:]  # a UNC path keeps one leading slash after the `//` prefix below
    if not text.startswith("/"):
        text = "/" + text
    body = "/" + text
    return f"Read({body.rstrip('/')}/**)" if is_dir else f"Read({body})"


def _protected(rel_key: str, read_path: str | None) -> list[str]:
    """Paths a session must always reach: its source + prepared file, the wiki (staging and live),
    the cache siblings of the wiki, the rules dirs and docs/."""
    out: list[Path] = [config.source_path_for_key(rel_key), config.wiki_dir(), config.WIKI_DIR, config.DOCS_DIR]
    out.append(config.PACKAGED_RULES_DIR)
    ws_rules = config.workspace_rules_dir()
    if ws_rules is not None:
        out.append(ws_rules)
    if read_path:
        out.append(Path(read_path).parent)
    for name in (".citadel_pdftext", ".citadel_transcripts", ".citadel_resume"):
        out.append(config.WIKI_DIR.parent / name)
    return [str(p) for p in out]


def _expand(directory: Path, keep: list[str], budget: list[int]) -> list[tuple[Path, bool]]:
    """``directory``'s entries minus every protected path in ``keep`` — descending only into the
    child that leads to one. Bounded by ``budget`` (a one-item list, decremented)."""
    out: list[tuple[Path, bool]] = []
    try:
        with os.scandir(directory) as it:
            children = sorted(it, key=lambda e: e.name)
    except OSError:
        return out
    for entry in children:
        if budget[0] <= 0:
            break
        budget[0] -= 1
        child = Path(entry.path)
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            is_dir = False
        if any(_within(str(child), k) for k in keep):
            continue  # the protected path itself (or inside one)
        if is_dir and any(_within(k, str(child)) for k in keep):
            out.extend(_expand(child, keep, budget))
        else:
            out.append((child, is_dir))
    return out


def session_rules(rel_key: str, read_path: str | None = None) -> tuple[list[str], int]:
    """This session's deny rules and how many entries the cap left unenforced."""
    entries = current()
    if not entries:
        return [], 0
    keep = _protected(rel_key, read_path)
    resolved: list[tuple[Path, bool]] = []
    budget = [_EXPAND_CAP]
    for path, is_dir in entries:
        text = str(path)
        if any(_within(text, k) for k in keep):
            continue
        if is_dir and any(_within(k, text) for k in keep):
            resolved.extend(_expand(path, keep, budget))
            continue
        resolved.append((path, is_dir))
    resolved.sort(key=lambda e: (not e[1], str(e[0])))
    rules = [rule_for(p, d) for p, d in resolved]
    return rules[:DENY_CAP], max(len(rules) - DENY_CAP, 0)


def write_settings(rules: list[str]) -> str:
    """Write the settings file (exactly ``{"permissions": {"deny": rules}}``) to a temp path and
    return it; the caller removes it after the session."""
    fd, path = tempfile.mkstemp(prefix="citadel_settings_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"permissions": {"deny": rules}}, fh)
    return path
