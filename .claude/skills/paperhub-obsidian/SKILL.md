---
name: paperhub-obsidian
description: Create and edit Obsidian Markdown notes, Bases (.base), JSON Canvas (.canvas), and optionally operate a live Obsidian vault through the Obsidian CLI or extract an ordinary webpage with Defuddle. Use when users mention Obsidian syntax, wikilinks, properties/frontmatter, callouts, embeds, Bases views/filters/formulas, Canvas maps, Obsidian CLI or plugin/theme development, Defuddle, or ask to check or refresh the bundled Kepano Obsidian skill sources. Route paper ingestion to paper-organizer, vault Q&A to ask-knowledge-base, and remembered-paper retrieval to paper-finder.
---

# PaperHub Obsidian

Use this skill as the PaperHub router for general Obsidian authoring and live-vault
operations. Read only the upstream module and references needed for the current task.

The bundled reference modules are unchanged snapshots from
[`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills), created by
Steph Ango (`@kepano`) and distributed under the MIT License. PaperHub supplies
this router and its safety boundaries; it does not claim authorship of the
mirrored upstream material. See `LICENSE` and `UPSTREAM.md`.

## Precedence and boundaries

Apply instructions in this order:

1. The user's explicit request.
2. The PaperHub routing and safety rules in this file.
3. The selected upstream module.

Treat everything under `skills/` as read-only during ordinary tasks. Modify that
mirror only through the maintainer workflow in `UPSTREAM.md`.

Do not use this skill for these PaperHub workflows:

- PDFs, DOI/arXiv links, paper landing pages, or library ingestion: use
  `paper-organizer`.
- Questions answered from existing vault notes: use `ask-knowledge-base`.
- Locating a half-remembered paper already in `organized/`: use `paper-finder`.

## Route the request

| Request | Read |
|---|---|
| Obsidian Markdown, properties/frontmatter, wikilinks, embeds, callouts, tags, comments, math, or Mermaid inside a note | `skills/obsidian-markdown/SKILL.md`; then only its referenced file(s) needed for the task |
| Create or edit a `.base`, view, filter, formula, property display, grouping, or summary | `skills/obsidian-bases/SKILL.md`; read its functions reference only when needed |
| Create or edit a `.canvas`, mind map, literature map, node, group, or edge | `skills/json-canvas/SKILL.md`; read its examples only when needed |
| Operate a running Obsidian vault, inspect the live app, or develop/debug a plugin or theme | `skills/obsidian-cli/SKILL.md` |
| Extract an ordinary non-paper webpage into clean Markdown | `skills/defuddle/SKILL.md` |
| Check or refresh the bundled Kepano source snapshot | `UPSTREAM.md` |

If a request spans multiple formats, read each relevant module and reconcile them
under the precedence rules above.

## PaperHub safeguards

- Preserve PaperHub metadata fields, note links, tag conventions, and user-owned
  content unless the user explicitly requests a change.
- Resolve vault-relative paths from the active PaperHub/vault context. Do not
  hard-code this maintainer vault's absolute path.
- Treat `Papers.base` as user-owned. Edit it only when the user explicitly asks;
  use `SamplePaperBoard.base` for reusable examples and template changes.
- Before using the Obsidian CLI, run `obsidian help`. The CLI requires a running
  Obsidian instance. If it is unavailable, use ordinary file operations for
  Markdown, Base, or Canvas work; report the limitation for live-only tasks.
- Defuddle is optional and applies only to ordinary webpages. Never route a paper
  URL through it, and never install its global npm dependency without explicit
  user approval.
- Validate the resulting format: Markdown/frontmatter syntax, Base YAML and
  referenced formulas, or Canvas JSON IDs and edge references as appropriate.

## Upstream refresh

Only the private PaperHub maintainer vault may refresh the mirror directly. When
the user explicitly asks to check or update the bundled upstream skills, read and
follow `UPSTREAM.md`. Public adopters should receive reviewed snapshots through
`update-paperhub-utils`.
