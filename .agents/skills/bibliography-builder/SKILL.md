---
name: bibliography-builder
description: Build or export PaperHub references from exact labels or Boolean tag selections. Triggers on build the bib, references.bib, BibTeX export, formatted references.md, Chicago author-date reference lists, Markdown footnote definitions, or adding PaperHub references to a target Markdown note.
---

# Bibliography Builder

Open `.claude/skills/bibliography-builder/SKILL.md` from the PaperHub root and
follow its canonical workflow. Preflight with the shared citation audit,
require a user choice for missing records, generate `references.bib` by
default, and use formatted Markdown only when explicitly requested. Route
target-note citation and footnote requests through the canonical skill's
`target-note-footnotes.md` handoff.
