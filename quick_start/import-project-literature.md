# Import an Existing Project Literature Collection

Use this workflow when a project already has a folder of papers, a BibTeX file, or both. PaperHub can turn that collection into a searchable, citation-ready batch without generating AI summaries. A project tag such as `proj_xxx` keeps the imported papers together for browsing and later bibliography updates.

## Prepare the Inputs

Decide on three things before starting:

- The absolute path to the paper folder or `.bib` file.
- A unique project tag, such as `proj_TVP`. Keep the same tag for the life of the project.
- A heading for the import inside `to_be_organized/papers to find.md`.

The source BibTeX file may already contain DOI or URL fields. The agent should reuse those links first, then search for and verify only the missing ones.

## Import the Collection

Run the following prompt from the PaperHub folder. Replace the placeholders before sending it:

```text
I want to import an existing project literature collection into PaperHub.

Source papers or BibTeX file: <absolute path>
Project tag: proj_xxx
Checklist: to_be_organized/papers to find.md
Checklist heading: <project name> import

Please use the paper-organizer and citation-resolver skills and complete this as a batch:

1. Extract every paper from the source. Reuse a DOI or URL already present in the BibTeX entry. When a link is missing, find an official DOI, journal, publisher, repository, or author-hosted paper page and verify it against the title plus an author or publication year.
2. Save one verified Markdown link per paper under the checklist heading. Preserve the source order and do not mark any item complete yet.
3. Check the existing PaperHub library before organizing anything. Separate existing papers from papers that are genuinely new.
4. For existing papers, keep their folders, set status to done, and add the tag proj_xxx without removing their current tags.
5. Process all new links as one batch with paper-organizer in link-metadata mode using the current coding agent. Do not create AI summaries. If I name another configured engine, use that engine instead.
6. Set each new paper's status to done and add the tag proj_xxx.
7. Resolve citation information for the full project batch with citation-resolver. Keep valid existing citation records unchanged.
8. Mark a checklist link with ✓ only after its PaperHub paper exists, its status is done, the project tag is present, and its citation record is valid. Leave unresolved items unchecked and report what still needs attention.

Report the total papers, existing papers reused, new papers added, citations resolved, unresolved papers, and completed checklist items.
```

For a large collection, the agent should parse and check the entire list first, then batch-process only the new papers. `link-metadata` mode creates the normal metadata note and public abstract but no interpretive summary.

## Add a Project View in Obsidian

This is a quick manual Obsidian step; the agent does not need to edit the board.

1. Open `SamplePaperBoard.base`.
2. Add a new view or duplicate an existing table view.
3. Name it after the project.
4. Add the filter **Tags contains `proj_xxx`**.
5. Choose the columns, grouping, and sorting that are useful for the project.

The view will continue to update as papers gain or lose the project tag.

## Maintain the Project

Use `proj_xxx` whenever you add another paper for the same project. The project view and later bibliography selections will pick it up automatically.

When the project's BibTeX file needs an update, give Bibliography Builder the file's absolute path:

```text
/bibliography-builder : add every PaperHub paper tagged proj_xxx to <absolute path to the existing project.bib>.

Run the citation preflight first. If any records are unresolved, ask whether to resolve them; do not silently omit papers. Stage the selected entries separately, preserve every existing entry and its formatting, skip confirmed duplicates by citation key or DOI, and stop for my decision if an identity conflict appears. After the merge, report the numbers added, skipped as duplicates, and left in conflict.
```

Bibliography Builder will not write directly over the existing database during staging. If the target file does not exist, ask it to build a new `references.bib` at the desired absolute path instead.
