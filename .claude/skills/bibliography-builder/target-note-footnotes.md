# Target-note reference handoff

Use this workflow only when the user supplies a target Markdown note and asks
the agent to add PaperHub citations, footnotes, or reference information. This
is one output use case; ordinary exact-label and tag-selected bibliography
requests remain in `SKILL.md`.

## Prepare the reference artifacts

1. Read the target note and identify the exact PaperHub papers used in it.
   Interpret the prose yourself; do not ask a script to edit or understand the
   note.
2. Build the explicit label manifest and run the normal citation preflight from
   `SKILL.md`.
3. Unless the user chooses other paths, write both artifacts beside the target
   note:

   ```bash
   cd paperhub_utils
   uv run python -m scripts.bibliography_builder \
     --labels-file /tmp/paperhub_selection.json \
     --format bibtex \
     --output /absolute/target/folder/references.bib

   uv run python -m scripts.bibliography_builder \
     --labels-file /tmp/paperhub_selection.json \
     --format reference-data \
     --output /absolute/target/folder/references.md
   ```

   Respect the normal partial-build and overwrite checkpoints. Use the
   filename explicitly requested by the user instead of `references.md` when
   applicable.

## Hand off to agent judgment

Read `references.md` and the target note, then make only the requested note
edits. Do not inspect the Python implementation during a routine run.

- Map each reference to an exact location in the prose.
- Preserve PaperHub wikilink targets and use readable author-year display text
  when it fits the sentence.
- By default, use numeric Markdown footnote identifiers in first-appearance
  order: `[^1]`, `[^2]`, and so on. Reuse the same number for later citations
  to the same paper. Keep PaperHub labels as stable BibTeX keys; do not expose
  them as footnote identifiers unless the user asks.
- Compose full, readable footnote definitions from the exported reference
  facts. The structured file is source material, not text that must be pasted
  verbatim.
- Preserve unrelated prose and existing footnotes. Never renumber unrelated
  numeric footnotes silently; resolve collisions from context or ask when the
  intended numbering is ambiguous.
- Do not add uncited papers to the note unless the user asks for a complete
  reference list.

After editing, verify that every inserted marker has exactly one definition,
every selected in-text paper has a marker, repeated papers reuse their number,
and both output files contain the intended paper set. Report any corrected or
uncertain citation fields.
