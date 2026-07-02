# delete — strip a removed source's provenance

The source was **removed from disk** and no longer exists. Do **NOT** try to open it. Remove the
provenance that depended on it:

1. Search the wiki (Grep/Glob/Read) for every page that cites it: a `resource:` frontmatter field
   naming it, or a `[^sN]` footnote whose `## Sources` definition links to it (e.g.
   `](../../raw/<the-file>)`).
2. For each fact whose **ONLY** source was that file, delete the sentence, its `[^sN]` marker,
   and its `## Sources` definition. If the SAME fact also carries another `[^sN]` source, keep
   the fact and remove ONLY this file's marker and definition.
3. If a page's `resource:` named the deleted file, repoint it to another raw file the page still
   cites; if no cited source remains, the page is unsupported — delete it and repoint or remove
   inbound links to it (`core.md` § Restructuring).
4. **Never invent replacement facts.**

When you finish, **no page may reference the deleted source** — the system re-checks and rolls
the whole cleanup back otherwise.
