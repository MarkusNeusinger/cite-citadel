"""Human command-line entry point mirroring the MCP tools.

``okf-wiki`` with six subcommands::

    okf-wiki ingest [paths ...]   # fold raw/ (or explicit paths) into the wiki
    okf-wiki serve                # run the MCP stdio server
    okf-wiki search <query> [--limit N] [--tag T]
    okf-wiki tags [tag]           # browse pages by tag
    okf-wiki lint [--stale-days N]
    okf-wiki view [--out PATH] [--no-open] [--obsidian]   # offline single-file HTML viewer

Exit codes are CI-friendly: ingest returns 1 if any source errored (a missing or
unusable LLM CLI surfaces as a per-source error in the report), lint returns 2 if
the report is not clean, and any RuntimeError raised by a subcommand prints to
stderr and returns 1.

``serve`` imports the MCP server lazily inside cmd_serve, so merely importing
this module never requires the ``mcp`` package.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Build the ``okf-wiki`` argument parser with its six subcommands."""
    parser = argparse.ArgumentParser(
        prog="okf-wiki",
        description="An LLM-maintained personal wiki in Google OKF, with an MCP search server.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest",
        help="Fold new/changed raw files into the wiki (default: all of raw/).",
    )
    p_ingest.add_argument(
        "paths",
        nargs="*",
        help="Specific files or directories to ingest (default: every *.md under raw/).",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_serve = sub.add_parser(
        "serve",
        help="Run the MCP stdio server (wiki_search/wiki_read/wiki_index/wiki_ingest).",
    )
    p_serve.set_defaults(func=cmd_serve)

    p_search = sub.add_parser(
        "search",
        help="Keyword search across the wiki pages.",
    )
    p_search.add_argument("query", help="Search query.")
    p_search.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of hits to return (default: 8).",
    )
    p_search.add_argument(
        "--tag",
        default=None,
        help="Restrict the search to pages carrying this tag (case-insensitive).",
    )
    p_search.set_defaults(func=cmd_search)

    p_tags = sub.add_parser(
        "tags",
        help="List all tags and the pages under each (browse the wiki by topic).",
    )
    p_tags.add_argument(
        "tag",
        nargs="?",
        default=None,
        help="Show only this tag's pages (default: list every tag).",
    )
    p_tags.set_defaults(func=cmd_tags)

    p_lint = sub.add_parser(
        "lint",
        help="Static health check (contradictions/orphans/missing-cites/broken-links/missing-type/stale).",
    )
    p_lint.add_argument(
        "--stale-days",
        type=int,
        default=365,
        help="Pages older than this many days are flagged stale (default: 365).",
    )
    p_lint.set_defaults(func=cmd_lint)

    p_view = sub.add_parser(
        "view",
        help="Generate and open a single-file, offline HTML viewer for the wiki.",
    )
    p_view.add_argument(
        "--out",
        default=None,
        help="Where to write the .html (default: wiki/.okf_viewer.html).",
    )
    p_view.add_argument(
        "--no-open",
        dest="open_browser",
        action="store_false",
        help="Write the file but do not launch a browser.",
    )
    p_view.add_argument(
        "--obsidian",
        action="store_true",
        help="Open the wiki folder as an Obsidian vault instead (best-effort deep link).",
    )
    p_view.set_defaults(func=cmd_view, open_browser=True)

    return parser


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run an ingest pass; return 1 if any source errored, else 0."""
    from . import ingest

    report = ingest.ingest(args.paths or None)
    print(report.render())
    return 1 if report.errors else 0


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


def cmd_view(args: argparse.Namespace) -> int:
    """Generate the offline single-file HTML viewer and open it (unless --no-open)."""
    from . import viewer

    return viewer.view(out=args.out, open_browser=args.open_browser, obsidian=args.obsidian)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the chosen subcommand.

    On a RuntimeError raised by a subcommand, print the message to stderr and
    return 1. (Ingest collects per-source LLM-CLI failures into its report
    instead of raising, so those exit 1 via report.errors.)
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
