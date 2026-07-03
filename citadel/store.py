"""Facade for the wiki 'database' — the ``wiki/`` directory loaded into memory.

**The ``wiki/`` directory IS the database**: no SQLite, no vector store. Pages are markdown files
with YAML frontmatter; search, index, graph, and provenance are recomputed from them in memory.
The implementation is split by responsibility across four sibling modules, which this module
re-exports as one public surface (importers keep using ``from . import store``):

- :mod:`citadel.store_core` — load / read / write / delete / search + the page/index/sources text
  providers and the append-only log writer.
- :mod:`citadel.linkgraph` — cross-link resolvers/rewriters, raw-source reference finders, and the
  inbound backlink map (the deterministic 'links keep working' machinery).
- :mod:`citadel.catalogs` — ``rebuild_indexes`` and the generated OKF nav files (index.md, the
  per-folder indexes, sources/index.md, open-points/index.md).
- :mod:`citadel.open_points` — parsing ``## Open Points`` threads and deriving their status.
"""

from __future__ import annotations

from .catalogs import (
    OPEN_POINTS_INDEX_REL,
    SOURCES_INDEX_REL,
    _render_open_points_catalog,
    _render_sources_catalog,
    rebuild_indexes,
)
from .linkgraph import (
    _link_points_at_key,
    _rewrite_body_links,
    _source_key_to_page_link,
    citing_pages_map,
    find_broken_links,
    find_raw_references,
    inbound_map,
    rewrite_links,
    rewrite_raw_references,
)
from .open_points import OpenPoint, collect_open_points, parse_open_points
from .store_core import (
    _is_skipped_name,
    append_log,
    delete_page,
    index_text,
    load,
    read_page,
    read_page_text,
    search,
    sources_text,
    tag_catalog,
    utc_now_iso,
    write_page,
)


__all__ = [
    # store_core: CRUD / search / text providers / log
    "utc_now_iso",
    "load",
    "search",
    "read_page",
    "read_page_text",
    "index_text",
    "sources_text",
    "write_page",
    "delete_page",
    "tag_catalog",
    "append_log",
    "_is_skipped_name",
    # linkgraph: resolvers / rewriters / reference finders / backlinks
    "rewrite_links",
    "rewrite_raw_references",
    "find_raw_references",
    "citing_pages_map",
    "find_broken_links",
    "inbound_map",
    "_rewrite_body_links",
    "_link_points_at_key",
    "_source_key_to_page_link",
    # catalogs: generated nav files
    "SOURCES_INDEX_REL",
    "OPEN_POINTS_INDEX_REL",
    "rebuild_indexes",
    "_render_sources_catalog",
    "_render_open_points_catalog",
    # open_points: thread parsing + status derivation
    "OpenPoint",
    "parse_open_points",
    "collect_open_points",
]
