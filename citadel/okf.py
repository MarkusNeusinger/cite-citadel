"""The OKF file format in ~80 lines.

Parse a markdown file into (frontmatter dict, body str) and serialize back,
byte-stable; validate the one required ``type`` field; slugify titles; render
relative cross-links; and the NON-NEGOTIABLE path-safety guard.

Knows nothing about the LLM, the store, or the filesystem layout.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


REQUIRED_FIELD = "type"


class OKFError(Exception):
    """Raised on an invalid OKF page or an unsafe path."""


@dataclass
class Page:
    rel_path: str  # e.g. 'concepts/transformer.md'
    frontmatter: dict
    body: str

    @property
    def type(self) -> str:
        return self.frontmatter.get("type", "")

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.rel_path)

    @property
    def description(self) -> str:
        return self.frontmatter.get("description", "")

    @property
    def tags(self) -> list[str]:
        return self.frontmatter.get("tags", []) or []


def parse(text: str) -> tuple[dict, str]:
    """Split a leading ``---\\n...\\n---\\n`` YAML block via ``yaml.safe_load``;
    return ``(frontmatter_dict, body)``. If there is no frontmatter block — or the
    block is malformed YAML — return ``({}, text)`` rather than raising, so one bad
    hand-edited page can't crash the whole wiki load. ``yaml.safe_load`` of an empty
    block -> ``{}``.

    A leading UTF-8 BOM (``\\ufeff``) and any blank lines above the opening fence are
    tolerated. A file written on Windows often acquires a BOM, and an agent occasionally
    leaves a blank line before the frontmatter; either one used to sit in front of the
    opening ``---`` and hide it, so the page parsed as having NO frontmatter and EVERY
    required field then read as missing. The BOM is stripped up front (an encoding
    artifact, never content), so even the no-frontmatter ``({}, text)`` fallback returns
    BOM-free text. Leading whitespace is only skipped internally to locate the fence: a
    matched body starts after the CLOSING fence, and the fallback body is otherwise
    returned unchanged (its leading whitespace preserved)."""
    # Strip a leading UTF-8 BOM first: it is an encoding artifact, never content, and would
    # otherwise precede the opening '---' and prevent the frontmatter from being recognized.
    if text.startswith("\ufeff"):
        text = text[1:]
    # Look for the opening fence past any leading blank lines / whitespace.
    head = text.lstrip()
    if head.startswith("---\n") or head == "---" or head.startswith("---\r\n"):
        # Normalise the opening fence and look for the closing fence.
        rest = head[len("---") :]
        # Strip a single newline right after the opening fence.
        if rest.startswith("\r\n"):
            rest = rest[2:]
        elif rest.startswith("\n"):
            rest = rest[1:]
        # Find the closing '---' line.
        match = re.search(r"(?m)^---[ \t]*\r?\n?", rest)
        if match is not None:
            fm_text = rest[: match.start()]
            body = rest[match.end() :]
            try:
                loaded = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                # Tolerate a malformed frontmatter block: treat the page as having
                # no usable frontmatter (lint then flags the missing 'type') rather
                # than letting one bad page crash the whole wiki load.
                return {}, text
            frontmatter = loaded if isinstance(loaded, dict) else {}
            return frontmatter, body
    return {}, text


def dump(frontmatter: dict, body: str) -> str:
    """Return ``'---\\n' + yaml.safe_dump(...) + '---\\n' + body``. Ensure the
    body ends with exactly one trailing newline."""
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    body = body.rstrip("\n") + "\n"
    return "---\n" + fm_text + "---\n" + body


def validate(frontmatter: dict) -> None:
    """Raise OKFError if ``type`` is missing or falsy."""
    if not frontmatter.get(REQUIRED_FIELD):
        raise OKFError(f"missing required field: {REQUIRED_FIELD!r}")


def slugify(title: str) -> str:
    """Lowercase, strip, replace runs of non-alphanumeric with ``-``, trim
    leading/trailing ``-``. Empty -> ``'untitled'``."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "untitled"


def folder_for_type(type_: str) -> str:
    """Route an OKF ``type`` to its wiki sub-folder. Case-insensitive on the known types;
    every unknown type falls through to ``misc``.

    | ``type``         | folder            |
    | ---------------- | ----------------- |
    | ``Concept``      | ``concepts``      |
    | ``Object``       | ``objects``       |
    | ``System``       | ``systems``       |
    | ``Person``       | ``persons``       |
    | ``Organization`` | ``organizations`` |
    | ``Project``      | ``projects``      |
    | ``Abbreviation`` | ``abbreviations`` |
    | ``Entity`` (legacy) | ``entities``   |
    | anything else    | ``misc``          |

    The set is split **by kind** so every page has exactly one home and even a small model can
    route without guessing (the "can you touch it?" test: a physical/engineered thing — a part,
    product, material, or device — is an ``Object``; a principle/method/topic is a ``Concept``; an
    external software system/service a source connects to — DB, API, queue, library — is a
    ``System``). ``Person``/``Organization``/``Project`` replace the old overloaded ``Entity``
    ("person, org, project, tool"). ``Entity`` is still routed to ``entities`` as a tolerated
    **legacy alias** so old pages keep working, but it should no longer be produced. The British
    spelling ``Organisation`` is accepted as an alias of ``Organization``."""
    normalized = (type_ or "").strip().lower()
    return {
        "concept": "concepts",
        "object": "objects",
        "system": "systems",
        "person": "persons",
        "organization": "organizations",
        "organisation": "organizations",  # British spelling — same folder
        "project": "projects",
        "abbreviation": "abbreviations",
        "entity": "entities",  # legacy alias — superseded by object/person/organization/project
    }.get(normalized, "misc")


# Title separators between an abbreviation's short form and its expansion, e.g.
# "TDS — Total Dissolved Solids". Longest/spaced first so " - " wins over a bare "-"
# that may sit inside the expansion itself.
_ABBR_TITLE_SEPS = (" — ", " – ", " - ", "—", "–")


def abbrev_short_long(page: "Page") -> tuple[str, str]:
    """Split an ``Abbreviation`` page into ``(short_form, expansion)``.

    The canonical title is ``"SHORT — Expansion"`` (em/en-dash or spaced hyphen), so both
    forms live in the highest-weighted search field and either one finds the page. Falls back
    to the first two ``aliases`` entries, then to ``(title, description)``. Used to render the
    generated glossary table (store) and to know which abbreviations are already defined (lint)."""
    title = page.title.strip()
    for sep in _ABBR_TITLE_SEPS:
        if sep in title:
            short, _, expansion = title.partition(sep)
            short, expansion = short.strip(), expansion.strip()
            if short and expansion:
                return short, expansion
    aliases = page.frontmatter.get("aliases") or []
    if isinstance(aliases, list):
        cleaned = [str(a).strip() for a in aliases if str(a).strip()]
        if len(cleaned) >= 2:
            return cleaned[0], cleaned[1]
    return title, page.description.strip()


def default_rel_path(type_: str, title: str) -> str:
    """``f'{folder_for_type(type_)}/{slugify(title)}.md'``."""
    return f"{folder_for_type(type_)}/{slugify(title)}.md"


def rel_path_between(from_rel: str, to_rel: str) -> str:
    """POSIX relative path FROM the page ``from_rel`` TO the page ``to_rel``.

    e.g. ``rel_path_between('concepts/a.md', 'entities/b.md')`` -> ``'../entities/b.md'``.
    The inverse of :func:`resolve_link`. Used to rewrite a cross-link's target when the
    page it points to is renamed/merged."""
    start = os.path.dirname(from_rel) or "."
    return os.path.relpath(to_rel, start=start).replace(os.sep, "/")


def resolve_link(from_rel: str, target: str) -> str:
    """Resolve a markdown link ``target`` written in page ``from_rel`` to a
    wiki-root-relative POSIX path.

    e.g. ``resolve_link('concepts/a.md', './b.md')`` -> ``'concepts/b.md'`` and
    ``resolve_link('concepts/a.md', '../entities/x.md')`` -> ``'entities/x.md'``. This is
    the single source of truth for turning a relative cross-link into a page identity,
    shared by lint (broken-link detection) and the store (link rewriting)."""
    base = os.path.dirname(from_rel)
    norm = os.path.normpath(os.path.join(base, target))
    return norm.replace(os.sep, "/")


def rel_link(from_rel: str, to_rel: str, text: str) -> str:
    """Render a markdown link ``'[text](RELPATH)'`` where RELPATH is the POSIX
    relative path from ``from_rel`` to ``to_rel``."""
    return f"[{text}]({rel_path_between(from_rel, to_rel)})"


def safe_join(base: Path, rel_path: str) -> Path:
    """REQUIRED HARDENING. Reject an absolute ``rel_path`` or any path that
    escapes ``base``. Reject empty, leading-``/``, or ``..``-segment paths.
    Return the resolved absolute Path."""
    if not rel_path:
        raise OKFError(f"unsafe path: {rel_path!r}")
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise OKFError(f"unsafe path: {rel_path!r}")
    candidate = Path(rel_path)
    if candidate.is_absolute():
        raise OKFError(f"unsafe path: {rel_path!r}")
    if ".." in candidate.parts:
        raise OKFError(f"unsafe path: {rel_path!r}")
    base_resolved = base.resolve()
    target = (base_resolved / rel_path).resolve()
    if not target.is_relative_to(base_resolved):
        raise OKFError(f"unsafe path: {rel_path!r}")
    return target
