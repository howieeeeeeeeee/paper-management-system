# Obsidian 101

PaperHub is an Obsidian-first paper library. Use a current Obsidian app with the Bases core plugin enabled. Each paper has one folder and one metadata note; that metadata note is the source of truth for links, reading status, tags, and Bases views.

## Obsidian Basics

- Use `[[note-name]]` links for papers, ideas, authors, and projects.
- Add `aliases:` when a paper has common short names, acronyms, or citation labels.
- Use YAML properties for anything you want to sort or filter in Bases.
- Use `tags:` for reusable categories; Obsidian and Bases can filter them directly.
- Keep `SamplePaperBoard.base` as the dashboard, and treat paper metadata notes as the source of truth.

## 1. Understand the Structure

```text
organized/
`-- melitz2003trade/
    |-- melitz_2003.pdf
    |-- melitz2003trade.md
    `-- ai_summary.md
```

A local or publicly downloaded PDF stays beside its metadata note when available.
Link-only folders may contain just the metadata note. The optional
`ai_summary.md` is supporting material; the metadata note remains the main
Obsidian object.

## 2. Link Papers

The metadata note is the paper's Obsidian handle. Mention a paper from any note with:

```md
[[melitz2003trade]]
[[melitz2003trade#Quick Reference]]
```

## 3. Track Reading

Edit the properties at the top of a paper note:

```yaml
status:
  - digesting
interest: high
tags:
  - industrial_organization
  - experimental
```

Use `status` for workflow, `interest` for priority, and `tags` for fields, methods, topics, courses, or projects.

## 4. Use `SamplePaperBoard.base`

Open `SamplePaperBoard.base` in Obsidian. Use the view menu in the top-left corner to switch views. Each view can have its own filters, visible properties, sort order, and grouping. This repo includes:

- `Backlog`: unfinished papers, filtered and grouped by `status`.
- `Digesting` and `Reflecting`: active reading queues.
- `Interesting Things`: papers with `interest: high`.
- `IO Papers`, `Human AI Papers`, `Experiment`: topic shelves based on tags.
- `All`: the full library sorted by recent edits.

Duplicate a view, then adjust Filters, Sort, Group, or Properties to make your own course, seminar, topic, or project board.

## Obsidian Tips

- Sync: keep the vault inside an iCloud Drive-synced folder, or another sync service you trust, so the same library is available on desktop and mobile. Avoid editing the same note on two devices before sync finishes, or you risk conflict copies.
- Overview: in Bases, combine filters such as status, tags, and interest with table or list views so one board can show active reading, methods shelves, or seminar queues. Start from `SamplePaperBoard.base` as a smaller example.
- Agent authoring: use [`paperhub-obsidian`](paperhub-obsidian.md) for Obsidian Markdown, Bases, Canvas maps, or optional live-vault CLI work.

## AI Integration

AI is the ingestion layer, not the library model. Put PDFs in `to_be_organized/`, then ask your coding agent:

```text
/paper-organizer : metadata-only batch for everything in `to_be_organized/` using (Agy CLI / Codex CLI / OpenRouter API).
```

Use `full summary` instead of `metadata-only` when you also want `ai_summary.md`. To customize generated metadata fields, edit [metadata_template.txt](../../paperhub_utils/prompts/shared/metadata_template.txt). For full-summary shape, edit [summary_full.txt](../../paperhub_utils/prompts/aspect/summary_full.txt). For shared style, edit [style.txt](../../paperhub_utils/prompts/shared/style.txt).

Further reading: [Properties](https://obsidian.md/help/properties), [Tags](https://obsidian.md/help/tags), [Internal links](https://obsidian.md/help/links), [Bases](https://obsidian.md/help/bases), [Bases views](https://obsidian.md/help/bases/views).
