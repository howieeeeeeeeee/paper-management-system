---
name: bibliography-builder
description: Build or extend a PaperHub bibliography from papers selected by exact labels or Boolean tag conditions. Use when the user asks to build/export a bib, create or add entries to references.bib or another existing BibTeX database, produce formatted references.md, create a Chicago author-date reference list or Markdown footnote definitions, or add PaperHub references and footnotes to a target Markdown note. BibTeX is the default; formatted Markdown is explicit and best-effort.
---

# Bibliography Builder

Build from per-paper `citation.csl.json` files. Never infer arbitrary English
inside scripts; translate the request into deterministic labels and tag flags.
Execute the supported scripts directly during routine use. Read their Python
source only for debugging or framework maintenance.

## Route the output

- For ordinary BibTeX or formatted reference-list requests, use the workflows
  below. Selection may come from exact labels or Boolean tag conditions.
- When the user supplies a target Markdown note and asks the agent to add
  citations, footnotes, or reference information to that note, read and follow
  `target-note-footnotes.md`.

## Select and preflight

Create an explicit ordered label manifest:

```bash
cd paperhub_utils
uv run python -m scripts.paper_select \
  --all-tag behavioral_economics \
  --output-manifest /tmp/paperhub_selection.json
```

Run the shared read-only audit before exporting:

```bash
cd paperhub_utils
uv run python -m scripts.citation_resolver audit \
  --labels-file /tmp/paperhub_selection.json \
  --report-file /tmp/paperhub_citation_audit.json
```

Show the counts and affected labels. If anything is unresolved, ask the user to
choose exactly one:

1. Resolve missing citations.
2. Build from ready papers only.
3. Cancel.

Do not resolve or omit silently. If resolution is chosen, follow
`citation-resolver`, rerun the audit, and ask again before a partial build when
anything remains unresolved.

## Build BibTeX by default

Collect an absolute output file or directory path. “Build the bib” means
`references.bib`.

```bash
cd paperhub_utils
uv run python -m scripts.bibliography_builder \
  --labels-file /tmp/paperhub_selection.json \
  --format bibtex \
  --output /absolute/path/references.bib
```

Add `--allow-partial` only after explicit partial-build approval. Add `--overwrite` only after explicit approval to replace an existing output. When the user asks to add entries to an existing `.bib`, do not use that file as the script output; follow the merge workflow below.

Entries use PaperHub labels as citation keys and sort by key for stable diffs.
Duplicate DOI records retain every requested key and produce a warning.

## Add to an existing BibTeX file

Treat “add,” “append,” or “merge” PaperHub papers into an existing `.bib` as an agent-handled merge:

1. Run the normal selection and citation preflight.
2. Build the selected ready papers to a new temporary `.bib`, never directly to the existing target.
3. Read both files and classify each staged entry. Skip a confirmed duplicate with the same citation key and identity, or the same normalized DOI under any key. Treat a reused key with a different DOI or title as a conflict. When no DOI exists, compare normalized title and year; treat uncertainty as a conflict.
4. Report counts for entries to add, duplicates to skip, and conflicts. Stop and ask the user before resolving any conflict; never replace an existing entry silently.
5. Append only the new entry blocks. Preserve the existing file byte-for-byte apart from the final separator and appended entries; do not reorder, reformat, or remove existing entries, comments, `@string`, or `@preamble` blocks. Use a safe atomic edit and verify every new key occurs once and all prior content remains.

If the target path does not exist, use the ordinary new-file build instead. Never use `--overwrite` to simulate a merge.

## Build formatted Markdown only when requested

For “formatted,” “human-readable,” or `references.md`, use:

```bash
cd paperhub_utils
uv run --extra formatted-citations python -m scripts.bibliography_builder \
  --labels-file /tmp/paperhub_selection.json \
  --format markdown \
  --style chicago-author-date \
  --output /absolute/path/references.md
```

The default hidden style is `CITATION_PREFERRED_STYLE`. Do not ask about style
during ordinary BibTeX generation. Formatted output is best-effort because
`citeproc-py` does not fully implement all CSL disambiguation and collapsing
features; `references.bib` is the reliable primary product.

For explicit Markdown footnote definitions, add `--footnote-definitions`.
Describe them as packaged bibliography entries, not authentic Chicago
notes-and-bibliography citations. Never insert markers into prose without the
target file, exact paper-to-location mapping, and explicit approval.

For reliable citation facts that an agent will read and adapt, avoid the
best-effort CSL formatter and export structured Markdown:

```bash
cd paperhub_utils
uv run python -m scripts.bibliography_builder \
  --labels-file /tmp/paperhub_selection.json \
  --format reference-data \
  --output /absolute/path/references.md
```

This format is not a citation style. It preserves readable authors, dates,
titles, venues, publication fields, DOI, and URL without requiring citeproc.

## Report

Report the absolute output path, included and omitted labels, partial status,
duplicate-DOI warnings, and whether formatted output used the best-effort path.
