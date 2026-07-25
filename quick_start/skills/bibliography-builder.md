# Bibliography Builder

Use `bibliography-builder` to export selected PaperHub papers. The normal output
is `references.bib`, a BibTeX database that can be used by LaTeX, Quarto,
Pandoc, reference managers, and many journal workflows.

## Build a BibTeX File

```text
/bibliography-builder : build references.bib from papers tagged behavioral_economics.
```

The builder first shows citation coverage. If some papers are not ready, it
asks whether to resolve them, export only ready papers, or cancel. It never
silently omits papers or changes citation records. It also asks before
overwriting an existing file.

BibTeX entries use each PaperHub paper label as the citation key and are sorted
for stable, reviewable changes. If two labels share a DOI, both requested keys
remain in the file and the builder reports a warning.

## Build a Readable Reference List

Request formatted Markdown explicitly:

```text
/bibliography-builder : create a human-readable references.md from papers tagged experiments.
```

The default reference list uses Chicago author-date formatting. This formatted
mode is best effort; use `references.bib` when you need the reliable,
portable source data.

Markdown footnote definitions are available when explicitly requested, but
they package reference-list entries rather than authentic Chicago
notes-and-bibliography citations.
