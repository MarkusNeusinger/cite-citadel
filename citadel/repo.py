"""Treat a git repository (or a folder marked ``.citadelsource``) under ``raw/`` as ONE source.

A code repo is not ingested file-by-file — that would spawn one agent session per file and bury
the wiki in per-function noise. Instead it is folded in as a single **digest**: the high-signal
files (README, dependency manifests, the connection/config layer, the data-transform / pipeline
core, entry points) concatenated up to a character budget, with ``.gitignore`` honored via
``git ls-files`` and obvious junk (lockfiles, minified bundles, ``node_modules``) filtered out.
The agent reads that digest and folds the repo into a few wiki pages answering: how to use it,
what it does, how it does it (the data flow), and what it outputs — plus a ``type: System`` page
per external system it touches.

**Versioning by commit.** A repo's identity is its HEAD commit (a dirty working tree appends a
short hash of the diff; a git-less snapshot uses an aggregate content hash). The manifest stores
that, so a later commit re-ingests only what changed — :func:`changed_files` feeds the reconcile
session the diff.

Everything here is pure/deterministic and shells out to ``git`` with a graceful fallback when git
is unavailable (a manual walk + a junk filter). No wiki state is touched here — the caller
(:mod:`citadel.ingest`) drives the session and the manifest.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config, manifest

# Opt-in marker: a folder carrying this file (even without a ``.git``) is treated as one source —
# for a copied snapshot that has no git history. Its identity is then an aggregate content hash.
MARKER = ".citadelsource"

# Bounded git calls — repo introspection should never hang an ingest run.
_GIT_TIMEOUT = 60

# Directories never worth reading (vendored deps, build output, caches). ``git ls-files`` already
# excludes most of these; the list is the safety net for the no-git fallback walk.
_SKIP_DIRS = {
    "node_modules", "dist", "build", "out", "target", "vendor", "__pycache__",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "coverage", ".next", ".nuxt", ".cache", "bower_components",
}

# Exact filenames to drop: lockfiles carry no human knowledge, only resolved version pins.
_EXCLUDE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "cargo.lock",
    "composer.lock", "gemfile.lock", "uv.lock", "go.sum", "podfile.lock",
}

# Filename patterns to drop: minified bundles, source maps, any *.lock.
_EXCLUDE_RE = re.compile(r"\.min\.(js|css)$|\.map$|\.lock$", re.IGNORECASE)

# Fence language hints by extension, for the digest's code blocks (cosmetic).
_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
    ".sql": "sql", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".sh": "bash", ".go": "go", ".rb": "ruby", ".java": "java", ".cs": "csharp", ".rs": "rust",
    ".php": "php", ".md": "markdown", ".ini": "ini", ".cfg": "ini",
}


def _git(repo: Path, *args: str) -> str | None:
    """Run ``git -C <repo> <args>`` and return stdout, or None on any failure (git missing, a
    non-zero exit, a timeout, or an OS error). Never raises — the caller falls back."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        proc = subprocess.run(
            [git, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def is_git_repo(path: Path) -> bool:
    """True if ``path`` is a git checkout — it holds a ``.git`` (a directory for a normal clone,
    or a file for a submodule / linked worktree). Pure filesystem check; needs no git binary."""
    return (Path(path) / ".git").exists()


def is_repo_dir(path: Path) -> bool:
    """True if ``path`` should be ingested as ONE repo source: a git checkout, or a folder
    carrying the opt-in :data:`MARKER` (a git-less snapshot the user wants treated as a unit)."""
    p = Path(path)
    return is_git_repo(p) or (p / MARKER).exists()


def head_commit(path: Path) -> str | None:
    """The repo's HEAD commit sha (full hex), or None if it cannot be read (no git, no commits)."""
    out = _git(Path(path), "rev-parse", "HEAD")
    out = (out or "").strip()
    return out or None


def is_dirty(path: Path) -> bool:
    """True if the working tree has uncommitted changes (``git status --porcelain`` non-empty)."""
    out = _git(Path(path), "status", "--porcelain")
    return bool(out and out.strip())


def remote_url(path: Path) -> str | None:
    """The ``origin`` remote URL, or None when there is no remote / no git. Used only as provenance
    metadata (recorded in the manifest); never required for ingest to work."""
    out = _git(Path(path), "remote", "get-url", "origin")
    out = (out or "").strip()
    return out or None


def _walk_repo(path: Path) -> list[str]:
    """Fallback file list when ``git ls-files`` is unavailable: every file under ``path`` (posix,
    relative to ``path``), skipping hidden entries and the junk directories in :data:`_SKIP_DIRS`."""
    root = Path(path)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d.lower() not in _SKIP_DIRS
        )
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            out.append(rel)
    return out


def list_files(path: Path) -> list[str]:
    """Repo-relative posix paths of the files to consider. Prefer ``git ls-files`` (which honors
    ``.gitignore`` and excludes ``node_modules``/build output); fall back to a filtered walk when
    git is unavailable or the dir is a non-git snapshot.

    ``--cached --others --exclude-standard`` lists BOTH tracked files and untracked-but-not-ignored
    ones, so a new pipeline script added to a dirty tree (which already triggers a re-ingest via
    :func:`identity`) is actually present in the digest — not silently dropped for being uncommitted."""
    if is_git_repo(path):
        out = _git(Path(path), "ls-files", "--cached", "--others", "--exclude-standard")
        if out is not None:
            return sorted({line for line in out.splitlines() if line.strip()})
    return sorted(_walk_repo(path))


def changed_files(path: Path, old_commit: str) -> list[str] | None:
    """Repo-relative paths changed between ``old_commit`` and HEAD (``git diff --name-only``), or
    None when a diff is impossible (no git, an unknown/snapshot ``old_commit``) so the caller
    re-digests the whole repo. A ``+dirty``/``snap.`` suffix on ``old_commit`` is stripped first;
    a ``snap.`` identity has no diffable base, so this returns None."""
    base = (old_commit or "").split("+", 1)[0]
    if not base or base.startswith("snap."):
        return None
    out = _git(Path(path), "diff", "--name-only", base, "HEAD")
    if out is None:
        return None
    return sorted(line for line in out.splitlines() if line.strip())


def _aggregate_hash(path: Path) -> str:
    """A short content hash over the (filtered) file list — name + per-file sha — used as the
    identity of a git-less snapshot, so editing any file re-ingests it. Streamed per file, so a
    large snapshot stays memory-bounded."""
    h = hashlib.sha256()
    root = Path(path)
    for rel in list_files(root):
        if _is_excluded(rel):
            continue
        h.update(rel.encode("utf-8", "replace"))
        h.update(b"\0")
        try:
            h.update(manifest.file_sha256(root / rel).encode("ascii"))
        except OSError:
            h.update(b"?")
        h.update(b"\n")
    return h.hexdigest()[:16]


def identity(path: Path) -> str:
    """The repo's version identity, stored in the manifest and compared to decide re-ingest:

    - a clean git checkout -> its HEAD commit sha;
    - a dirty git checkout -> ``"<commit>+dirty.<hash>"`` (a short hash of the diff + status), so
      uncommitted edits trigger a re-ingest instead of being missed;
    - a git-less snapshot (or git unavailable) -> ``"snap.<aggregate-hash>"``.
    """
    commit = head_commit(path)
    if commit:
        if is_dirty(path):
            diff = _git(Path(path), "diff", "HEAD") or ""
            status = _git(Path(path), "status", "--porcelain") or ""
            digest = hashlib.sha256((diff + "\0" + status).encode("utf-8", "replace")).hexdigest()
            return f"{commit}+dirty.{digest[:12]}"
        return commit
    return "snap." + _aggregate_hash(path)


def _is_excluded(rel: str) -> bool:
    """True if ``rel`` is junk to omit from the digest entirely: a lockfile, a minified bundle / map,
    or anything under a vendored/build directory (a safety net for the no-git walk)."""
    name = rel.rsplit("/", 1)[-1].lower()
    if name in _EXCLUDE_NAMES or _EXCLUDE_RE.search(name):
        return True
    parts = rel.lower().split("/")
    return any(p in _SKIP_DIRS or p == ".git" for p in parts)


# Path/name signals for the data-transform / connection core — the operationally valuable code.
_CORE_RE = re.compile(
    r"(transform|mapping|/map|etl|parse|convert|normaliz|/clean|loader|extract|pipeline"
    r"|connector|adapter|/client|repositor|/dao|schema|migrat|/model|/models|/query|/queries"
    r"|database|/db|ingest|fetch|sync|import|export)",
    re.IGNORECASE,
)
_MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "go.mod", "cargo.toml",
    "pom.xml", "build.gradle", "gemfile", "composer.json", "pipfile",
}
_ENTRY_NAMES = {
    "main.py", "app.py", "__main__.py", "cli.py", "server.py", "manage.py",
    "index.js", "index.ts", "main.js", "main.ts", "main.go", "app.ts", "app.js", "server.js",
}
_CONFIG_EXT = (".ini", ".cfg", ".toml", ".yaml", ".yml", ".env", ".conf")
_CODE_EXT = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".cs", ".rs", ".php",
    ".scala", ".kt", ".sh", ".sql",
)
_PROSE_EXT = (".md", ".txt", ".rst")


def _score(rel: str) -> int:
    """Signal tier for a file (higher = inlined sooner / more likely to fit the budget). The
    transform/connection core ranks highest — that is the knowledge these repos exist for; then
    docs and dependency manifests; then config and entry points; then ordinary source; then prose."""
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    if _CORE_RE.search("/" + low) or low.endswith(".sql"):
        return 5
    if name.startswith("readme") or name.startswith("architecture") or "/docs/" in "/" + low:
        return 4
    if name in _MANIFEST_NAMES or name.startswith("requirements"):
        return 4
    if name == "dockerfile" or name.startswith("docker-compose") or name.endswith(".env.example"):
        return 3
    if low.endswith(_CONFIG_EXT) or name in _ENTRY_NAMES:
        return 3
    if low.endswith(_CODE_EXT):
        return 2
    if low.endswith(_PROSE_EXT):
        return 1
    return 0


def _lang_for(rel: str) -> str:
    """Fence language hint for ``rel`` by extension (cosmetic; empty when unknown)."""
    ext = os.path.splitext(rel)[1].lower()
    return _LANG.get(ext, "")


def _read_text(abs_path: Path, limit: int) -> str | None:
    """Read ``abs_path`` as UTF-8 text (errors replaced), truncated to ``limit`` chars with a
    marker. None if it cannot be read or looks binary (a NUL byte in the first 64 KiB).

    Only a bounded PREFIX is read from disk — ``max(64 KiB, limit*4 + 64)`` bytes, enough for the
    binary sniff and for ``limit`` characters even in worst-case 4-byte UTF-8 — so a large file that
    slipped past the exclude filters never loads wholesale into memory."""
    read_cap = max(65536, limit * 4 + 64)
    try:
        with open(abs_path, "rb") as fh:
            data = fh.read(read_cap)
    except OSError:
        return None
    if b"\x00" in data[:65536]:
        return None
    text = data.decode("utf-8", "replace")
    # Either more characters than the cap, or the on-disk file was longer than the bytes we read.
    if len(text) > limit or len(data) >= read_cap:
        text = text[:limit].rstrip() + "\n... [truncated]"
    return text


# Headroom reserved below ``max_chars`` while inlining file contents, so the trailing "## Omitted"
# note still fits inside the budget after the loop fills it.
_FOOTER_RESERVE = 200


def _fit_block(rel: str, text: str, budget: int) -> str | None:
    """A fenced ``### rel`` code block whose TOTAL length is ``<= budget`` — the file's ``text`` is
    truncated with a marker to fit — or None when even a near-empty block would not fit. This is
    what makes the digest honor ``max_chars`` strictly: no single block (not even the first) can
    push the digest past the budget."""
    lang = _lang_for(rel)
    marker = "\n... [truncated]"
    scaffold = f"\n### {rel}\n```{lang}\n\n```\n"  # the block with an empty body
    if budget <= len(scaffold) + len(marker):
        return None
    room = budget - len(scaffold)
    if len(text) > room:
        text = text[: max(0, room - len(marker))].rstrip() + marker
    return f"\n### {rel}\n```{lang}\n{text}\n```\n"


def build_digest(
    path: Path,
    key: str,
    *,
    only: list[str] | None = None,
    change_summary: str | None = None,
    max_chars: int | None = None,
    per_file_chars: int | None = None,
) -> str:
    """Assemble the digest text the agent reads for repo source ``key`` (its source-of-record path,
    e.g. ``raw/acme-service``).

    The digest is: a header (the repo key, commit, remote, and — on reconcile — a change summary),
    a filtered file listing (so the agent sees structure), then the highest-signal file contents
    inlined in score order until the ``max_chars`` budget is hit (each file capped to
    ``per_file_chars``). Excluded junk (lockfiles, minified, vendored) never appears. ``only`` (the
    changed files on a reconcile) restricts the inlined contents to that set; everything still
    fits in one budgeted document.
    """
    root = Path(path)
    max_chars = max_chars if max_chars is not None else config.REPO_DIGEST_MAX_CHARS
    per_file_chars = (
        per_file_chars if per_file_chars is not None else config.REPO_PER_FILE_MAX_CHARS
    )

    all_files = [f for f in list_files(root) if not _is_excluded(f)]
    inline_set = set(only) if only is not None else None
    candidates = [f for f in all_files if inline_set is None or f in inline_set]
    candidates.sort(key=lambda f: (-_score(f), f))

    commit = identity(path)
    remote = remote_url(path)

    head = f"# Repository digest: {key}\n\n- commit/version: {commit}\n"
    if remote:
        head += f"- remote: {remote}\n"
    head += (
        "\nThis is a DIGEST of one git repository's high-signal files (lockfiles, vendored deps "
        "and build output omitted). Capture only what a knowledge wiki needs: how to use it, what "
        "it does, how it does it (the data flow), and what it outputs.\n"
    )
    if change_summary:
        # The change list never dominates the budget (a huge diff would otherwise crowd out content).
        summary = change_summary.rstrip()
        cap = max(0, max_chars // 4)
        if len(summary) > cap:
            summary = summary[:cap].rstrip() + "\n... [change list truncated]"
        head += "\n## What changed since the last ingest\n" + summary + "\n"

    parts: list[str] = [head]
    used = len(head)

    # File listing — capped to a bounded share of the remaining budget so a huge repo's path list
    # alone can't blow the cap (the contents below are where the value is).
    listing_header, listing_footer = "\n## Files\n", "\n"
    listing_budget = max(
        0, int((max_chars - used) * 0.4) - len(listing_header) - len(listing_footer)
    )
    listing_body = "\n".join(all_files)
    listing_truncated = False
    if len(listing_body) > listing_budget:
        clipped = listing_body[:listing_budget]
        listing_body = clipped.rsplit("\n", 1)[0] if "\n" in clipped else ""
        listing_truncated = True
    listing = (
        listing_header
        + listing_body
        + ("\n... [listing truncated]" if listing_truncated else "")
        + listing_footer
    )
    parts.append(listing)
    used += len(listing)

    # Inline file contents up to the budget (less a small footer reserve), highest-signal first.
    # Every block is trimmed to the remaining budget by _fit_block, so the digest never exceeds it.
    included: list[str] = []
    omitted: list[str] = []
    content_cap = max(0, max_chars - _FOOTER_RESERVE)
    contents_header = "\n## File contents\n"
    if used + len(contents_header) <= content_cap:
        parts.append(contents_header)
        used += len(contents_header)
        for rel in candidates:
            text = _read_text(root / rel, per_file_chars)
            if text is None:
                continue  # binary/unreadable — not knowledge
            block = _fit_block(rel, text, content_cap - used)
            if block is None:
                omitted.append(rel)
                continue
            parts.append(block)
            used += len(block)
            included.append(rel)
    else:
        omitted = list(candidates)

    if omitted:
        full = (
            f"\n## Omitted ({len(omitted)} files — budget/low-signal, read from {key} if needed)\n"
            + "\n".join(omitted)
            + "\n"
        )
        short = f"\n## Omitted: {len(omitted)} files (budget/low-signal)\n"
        if used + len(full) <= max_chars:
            parts.append(full)
        elif used + len(short) <= max_chars:
            parts.append(short)

    digest = "".join(parts)
    # Belt-and-suspenders: guarantee the hard cap even on a degenerate tiny budget.
    return digest[:max_chars]
