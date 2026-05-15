# Obsidian 101 for PaperHub

PaperHub stores each paper as a small folder under `organized/<paper_label>/`. Inside you get the PDF, a metadata note named `<paper_label>.md`, and optionally `ai_summary.md`.

## Links and navigation

- Open the metadata note for a paper. Its title matches the `paper_label`, so you can link to it from anywhere in the vault with a wikilink: `[[paper_label]]`.
- Keep the PDF in the same folder as the metadata note. If you move files, update links and any Bases filters that pointed at old paths.

## Properties you will edit

The metadata note has YAML frontmatter (Obsidian **Properties**) such as `title`, `authors`, `status`, `interest`, `tags`, and `journal`. Edit these like a normal note: they drive how papers show up in Bases tables and filters.

## Bases dashboard

- Open `Papers.base` in Obsidian (Bases core plugin). It is a starter board with views over your library folder.
- Filters use **paths relative to the vault root**. After you clone or move PaperHub, update the `file.inFolder(...)` strings in `Papers.base` (and `SamplePaperBoard.base` if you use it) so they match where this repo lives inside your vault—for example `PaperHub/organized` if the repo folder is named `PaperHub`.

## Where PDFs land before organizing

Drop new PDFs in `to_be_organized/`. After a skill run, papers appear under `organized/<paper_label>/` with notes ready for reading and tagging.
