"""Human command-line entry point mirroring the MCP tools.

``citadel`` with its subcommands::

    citadel init [DIR]           # scaffold a workspace (citadel.toml marker, .env, raw/, wiki/)
    citadel ingest [paths ...]   # fold raw/ (or explicit paths) into the wiki
    citadel serve                # run the MCP stdio server
    citadel search <query> [--limit N] [--tag T]
    citadel tags [tag]           # browse pages by tag
    citadel lint [--stale-days N]
    citadel check [paths ...]    # validate links/format/required-fields (the ingest gate)
    citadel view [--out PATH] [--no-open] [--obsidian]   # offline single-file HTML viewer
    citadel rules list|show|eject   # inspect / fork the rules files the ingest agent reads

Every subcommand except ``init`` and ``rules`` needs a resolved WORKSPACE (see config's discovery
order); ``main`` fails loud with exit 2 — pointing at ``citadel init`` and ``CITADEL_WORKSPACE``
— when none was found, instead of silently operating on a random CWD. ``rules list``/``show``
work workspace-less over the packaged defaults (handy for a pip user before ``init``); ``rules
eject`` checks for a workspace itself (the copy has nowhere to land without one).

Exit codes are CI-friendly: ingest returns 1 if any source errored OR a structural
problem remains (a broken cross-link or a page that failed validation — a missing or
unusable LLM CLI also surfaces as a per-source error), lint returns 2 if the report is
not clean, check returns 1 on any validation error, and any RuntimeError raised by a
subcommand prints to stderr and returns 1.

``serve`` imports the MCP server lazily inside cmd_serve, so merely importing
this module never requires the ``mcp`` package.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the ``citadel`` argument parser with its eight subcommands."""
    parser = argparse.ArgumentParser(
        prog="citadel", description="An LLM-maintained personal wiki in Google OKF, with an MCP search server."
    )
    # `--version` exits inside parse_args (like --help), so it works everywhere — including
    # a bare CWD with no workspace: main's fail-loud guard is never reached.
    parser.add_argument("--version", action="version", version=f"citadel {__version__}")
    # Every subcommand needs a resolved workspace unless it opts out (init, which CREATES one).
    parser.set_defaults(needs_workspace=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a citadel workspace (citadel.toml marker, .env, raw/, wiki/).")
    p_init.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Directory to initialize (created if missing; default: the current directory).",
    )
    p_init.set_defaults(func=cmd_init, needs_workspace=False)

    p_ingest = sub.add_parser("ingest", help="Fold new/changed raw files into the wiki (default: all of raw/).")
    p_ingest.add_argument(
        "paths",
        nargs="*",
        help="Specific files or directories to ingest (default: every file under raw/, recursively, any type).",
    )
    p_ingest.add_argument(
        "--quiet", action="store_true", help="Suppress the live per-file progress output (just print the final report)."
    )
    p_ingest.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Stream each LLM agent session's output live to the terminal (see exactly what the "
        "model does). copilot/gemini show their full transcript; the claude CLI only emits its "
        "final result envelope — use --log-dir for a full claude record. Disables the spinner.",
    )
    p_ingest.add_argument(
        "--log-dir",
        default=None,
        metavar="DIR",
        help="Write a transcript file per source (prompt + full CLI output + exit/duration) to "
        "DIR, so you can inspect what the model did even in headless mode. Overrides "
        "CITADEL_LLM_LOG_DIR.",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_serve = sub.add_parser("serve", help="Run the MCP stdio server (wiki_search/wiki_read/wiki_index/wiki_ingest).")
    p_serve.set_defaults(func=cmd_serve)

    p_search = sub.add_parser("search", help="Keyword search across the wiki pages.")
    p_search.add_argument("query", help="Search query.")
    p_search.add_argument("--limit", type=int, default=8, help="Maximum number of hits to return (default: 8).")
    p_search.add_argument(
        "--tag", default=None, help="Restrict the search to pages carrying this tag (case-insensitive)."
    )
    p_search.set_defaults(func=cmd_search)

    p_tags = sub.add_parser("tags", help="List all tags and the pages under each (browse the wiki by topic).")
    p_tags.add_argument("tag", nargs="?", default=None, help="Show only this tag's pages (default: list every tag).")
    p_tags.set_defaults(func=cmd_tags)

    p_lint = sub.add_parser(
        "lint", help="Static health check (contradictions/orphans/missing-cites/broken-links/missing-type/stale)."
    )
    p_lint.add_argument(
        "--stale-days", type=int, default=365, help="Pages older than this many days are flagged stale (default: 365)."
    )
    p_lint.set_defaults(func=cmd_lint)

    p_check = sub.add_parser("check", help="Validate page links, file format, and required fields (the ingest gate).")
    p_check.add_argument(
        "paths", nargs="*", help="Wiki pages to check (rel_path or file path); default: the whole wiki."
    )
    p_check.set_defaults(func=cmd_check)

    p_view = sub.add_parser("view", help="Generate and open a single-file, offline HTML viewer for the wiki.")
    p_view.add_argument("--out", default=None, help="Where to write the .html (default: wiki/.citadel_viewer.html).")
    p_view.add_argument(
        "--no-open", dest="open_browser", action="store_false", help="Write the file but do not launch a browser."
    )
    p_view.add_argument(
        "--obsidian",
        action="store_true",
        help="Open the wiki folder as an Obsidian vault instead (best-effort deep link).",
    )
    p_view.set_defaults(func=cmd_view, open_browser=True)

    p_rules = sub.add_parser("rules", help="Inspect and customize the rules files the ingest agent reads.")
    rules_sub = p_rules.add_subparsers(dest="rules_command", required=True)
    p_rules_list = rules_sub.add_parser(
        "list", help="List every effective rules file (a workspace rules/ override shadows the packaged one)."
    )
    p_rules_list.set_defaults(func=cmd_rules_list, needs_workspace=False)
    p_rules_show = rules_sub.add_parser("show", help="Print one effective rules file.")
    p_rules_show.add_argument("relname", help="Tree-relative rules file name, e.g. core.md or genres/email.md.")
    p_rules_show.set_defaults(func=cmd_rules_show, needs_workspace=False)
    p_rules_eject = rules_sub.add_parser(
        "eject",
        help="Copy a packaged rules file into the workspace rules/ for editing (the copy shadows the "
        "packaged file and is yours; it no longer updates with pip). Refuses to overwrite.",
    )
    p_rules_eject.add_argument("relname", help="Tree-relative rules file name, e.g. core.md or genres/email.md.")
    p_rules_eject.set_defaults(func=cmd_rules_eject, needs_workspace=False)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a workspace at DIR (default: CWD). Idempotent — existing files/dirs are reported
    as skipped, never overwritten — and always exits 0 (a fully-initialized workspace is not an
    error)."""
    from pathlib import Path

    from . import workspace

    root, results = workspace.init_workspace(Path(args.dir))
    print(f"Workspace: {root}")
    for status, name in results:
        print(f"  {status} {name}")
    if all(status == "skipped" for status, _ in results):
        print("Nothing to do — the workspace is already initialized.")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run an ingest pass (with live progress unless --quiet); 1 if any source errored.

    ``--verbose`` and ``--log-dir`` flip the observability knobs in ``config`` (read at call time by
    ``llm._run_session``): verbose streams each agent session live to the terminal, and log-dir
    writes a per-source transcript. With ``--verbose`` the spinner is suppressed so the streamed
    transcript is not overwritten by the in-place progress line."""
    from . import config, ingest

    if args.verbose:
        config.LLM_VERBOSE = True
    # `is not None` (not truthiness) so an explicit `--log-dir ""` is honored as "disable logging"
    # — the documented override — rather than silently falling through to CITADEL_LLM_LOG_DIR.
    if args.log_dir is not None:
        config.LLM_LOG_DIR = args.log_dir

    progress = None
    if not args.quiet:
        from .progress import ConsoleProgress

        # Base spinner suppression on the RESOLVED verbose state (config), so a session enabled via
        # CITADEL_LLM_VERBOSE — not just the --verbose flag — also drops the spinner that would
        # otherwise clobber the streamed transcript.
        progress = ConsoleProgress(spinner=not config.LLM_VERBOSE)
    report = ingest.ingest(args.paths or None, progress=progress)
    print(report.render())
    # Non-zero on a per-source error OR a structural problem left behind (a broken
    # cross-link the agent introduced) — so ingest gates the wiki's integrity in CI.
    return 1 if (report.errors or report.broken_links) else 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch the MCP stdio server (lazy import so importing cli needs no mcp)."""
    from .server import main as serve_main

    serve_main()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Print ranked search hits for the query (optionally filtered to a tag); return 0."""
    from . import store

    pages = None
    if args.tag:
        want = args.tag.strip().lower()
        pages = [p for p in store.load() if want in [str(t).lower() for t in p.tags]]
        if not pages:
            print(f"No pages tagged {args.tag!r}.")
            return 0

    hits = store.search(args.query, pages=pages, limit=args.limit)
    if not hits:
        scope = f" (tag {args.tag!r})" if args.tag else ""
        print(f"No matches for {args.query!r}{scope}.")
        return 0
    for page, score in hits:
        snippet = " ".join(page.body.split())[:120]
        tags = (" [" + ", ".join(page.tags) + "]") if page.tags else ""
        print(f"{page.rel_path}\t{page.title}\t{score:.2f}{tags}")
        if snippet:
            print(f"    {snippet}")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    """List all tags and their pages (or just one tag's pages); return 0."""
    from . import store

    catalog = store.tag_catalog()
    if not catalog:
        print("No tags yet.")
        return 0

    if args.tag:
        want = args.tag.strip().lower()
        pages = catalog.get(want)
        if not pages:
            print(f"No pages tagged {args.tag!r}.")
            return 0
        print(f"# {want} ({len(pages)})")
        for page in pages:
            print(f"- {page.rel_path}\t{page.title}")
        return 0

    for tag in sorted(catalog):
        pages = catalog[tag]
        print(f"{tag} ({len(pages)})")
        for page in pages:
            print(f"    {page.rel_path}\t{page.title}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    """Print the lint report; return 0 if clean, else 2."""
    from . import lint

    report = lint.lint(stale_days=args.stale_days)
    print(report.render())
    return 0 if report.ok() else 2


def cmd_check(args: argparse.Namespace) -> int:
    """Validate the wiki (or specific pages) for links/format/required-fields; print the
    issues and return 1 if any error. This is the strict per-page gate the ingest agent runs
    on its own edits before finishing."""
    import os
    from pathlib import Path

    from . import config, validate

    issues = validate.validate_all()
    if args.paths:
        wiki_root = config.WIKI_DIR.resolve()
        wanted: set[str] = set()
        for arg in args.paths:
            rel = arg.replace(os.sep, "/")
            try:
                resolved = Path(arg).resolve()
                if resolved.is_relative_to(wiki_root):
                    rel = str(resolved.relative_to(wiki_root)).replace(os.sep, "/")
            except (OSError, ValueError):
                pass
            wanted.add(rel)
        issues = [i for i in issues if i.rel_path in wanted]
    print(validate.render_issues(issues))
    return 1 if validate.has_errors(issues) else 0


def _rules_relname(arg: str) -> str:
    """Normalize a user-supplied tree-relative rules name to forward slashes and validate it:
    absolute paths, drive letters, and any ``..``/``.`` step are rejected, so ``rules show`` /
    ``rules eject`` can never reach outside the rules trees."""
    text = arg.replace("\\", "/").strip()
    parts = [p for p in text.split("/") if p]
    if not parts or text.startswith("/") or any(p in ("..", ".") for p in parts) or ":" in text:
        raise RuntimeError(f"invalid rules file name: {arg!r} (expected e.g. core.md or genres/email.md)")
    return "/".join(parts)


def _rules_layer(path, workspace_rules) -> str:
    """Which layer an effective rules path resolved from: ``workspace`` or ``packaged``."""
    from . import config

    if workspace_rules is not None:
        try:
            config._safe_resolve(path).relative_to(config._safe_resolve(workspace_rules))
            return "workspace"
        except ValueError:
            pass
    return "packaged"


def cmd_rules_list(args: argparse.Namespace) -> int:
    """One line per EFFECTIVE rules file — tree-relative name, origin layer (packaged|workspace),
    and its first (description) line. Works without a workspace: it then lists the packaged
    defaults only."""
    from . import config

    ws = config.workspace_rules_dir()
    names = config.rules_relnames()
    if not names:
        print("No rules files found.")
        return 0
    for rel in names:
        path = config.effective_rules_file(rel)
        try:
            first = next((line.lstrip("#").strip() for line in path.read_text(encoding="utf-8").splitlines()), "")
        except OSError:
            first = ""
        print(f"{rel}\t{_rules_layer(path, ws)}\t{first}")
    return 0


def cmd_rules_show(args: argparse.Namespace) -> int:
    """Print ONE effective rules file's content (workspace override when present, else the
    packaged default). Works without a workspace (packaged defaults)."""
    from . import config

    rel = _rules_relname(args.relname)
    path = config.effective_rules_file(rel)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise RuntimeError(f"no rules file named {rel!r} (see `citadel rules list`)") from None
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_rules_eject(args: argparse.Namespace) -> int:
    """Copy a PACKAGED rules file into the workspace ``rules/`` so it can be edited — the copy
    then shadows the packaged file (first-hit-wins) and is owned by the user (it no longer
    updates with pip). Never overwrites an existing workspace file."""
    from . import config

    rel = _rules_relname(args.relname)
    ws = config.workspace_rules_dir()
    if ws is None:
        raise RuntimeError(
            "`citadel rules eject` needs a workspace (the copy lands in <workspace>/rules/) — "
            "run `citadel init [DIR]` or set CITADEL_WORKSPACE first."
        )
    src = config.PACKAGED_RULES_DIR / rel
    if not src.is_file():
        raise RuntimeError(f"no packaged rules file named {rel!r} (see `citadel rules list`)")
    dest = ws / rel
    if dest.exists():
        raise RuntimeError(f"refusing to overwrite {dest} - it is already ejected; edit or remove it")
    config.robust_mkdir(dest.parent)
    dest.write_bytes(src.read_bytes())
    print(f"ejected {rel} -> {dest}")
    print("This copy now shadows the packaged file and is yours to edit; it no longer updates with pip.")
    return 0


def cmd_view(args: argparse.Namespace) -> int:
    """Generate the offline single-file HTML viewer and open it (unless --no-open)."""
    from . import viewer

    return viewer.view(out=args.out, open_browser=args.open_browser, obsidian=args.obsidian)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the chosen subcommand.

    Every subcommand that operates on a workspace declares ``needs_workspace=True`` (the parser
    default), so when discovery found none (``config.WORKSPACE_FOUND`` is False and
    ``WORKSPACE_ROOT`` is only the bare-CWD fallback) main aborts with an actionable error
    instead of silently reading/writing a wiki in whatever directory the process happens to run
    from (the pip-installed phantom-workspace bug class). ``--help`` and ``--version`` never
    reach the guard (argparse exits first), and ``init`` opts out — it CREATES the workspace.

    On a RuntimeError raised by a subcommand, print the message to stderr and
    return 1. (Ingest collects per-source LLM-CLI failures into its report
    instead of raising, so those exit 1 via report.errors.)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    from . import config

    if getattr(args, "needs_workspace", True) and not config.WORKSPACE_FOUND:
        print(
            "error: no citadel workspace found — this command needs one.\n"
            f"  No {config.WORKSPACE_MARKER} marker exists in the current directory or any parent, and no\n"
            "  CITADEL_WIKI_DIR + CITADEL_RAW_DIR pair is set.\n"
            "  Fix: run `citadel init [DIR]` to create a workspace, `cd` into an existing one, or set\n"
            "  CITADEL_WORKSPACE=/path/to/workspace (e.g. in your MCP host config for `citadel serve`).",
            file=sys.stderr,
        )
        return 2

    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
