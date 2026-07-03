"""Facade for the wiki 'database': one ``from . import store`` re-export of the public surface of
:mod:`citadel.store_core` (CRUD / search / text providers / log), :mod:`citadel.linkgraph` (the
cross-link graph), :mod:`citadel.catalogs` (generated OKF nav) and :mod:`citadel.open_points`
(``## Open Points`` thread parsing) — see each submodule's docstring for the detail.
"""

from __future__ import annotations

from .catalogs import OPEN_POINTS_INDEX_REL, SOURCES_INDEX_REL, rebuild_indexes
from .linkgraph import (
    citing_pages_map,
    find_broken_links,
    find_raw_references,
    inbound_map,
    rewrite_links,
    rewrite_raw_references,
    source_key_to_page_link,
)
from .open_points import OpenPoint, collect_open_points, parse_open_points
from .store_core import (
    append_log,
    delete_page,
    index_text,
    is_skipped_name,
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
    "is_skipped_name",
    # linkgraph: resolvers / rewriters / reference finders / backlinks
    "rewrite_links",
    "rewrite_raw_references",
    "find_raw_references",
    "citing_pages_map",
    "find_broken_links",
    "inbound_map",
    "source_key_to_page_link",
    # catalogs: generated nav files
    "SOURCES_INDEX_REL",
    "OPEN_POINTS_INDEX_REL",
    "rebuild_indexes",
    # open_points: thread parsing + status derivation
    "OpenPoint",
    "parse_open_points",
    "collect_open_points",
]
