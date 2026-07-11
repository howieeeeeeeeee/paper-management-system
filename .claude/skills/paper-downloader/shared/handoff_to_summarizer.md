# Handoff to paper-organizer

Run this after a PDF (and its `{stem}.citation.md` sidecar) has landed in
`to_be_organized/`.

## Ask whether to summarize now

**AskUserQuestion:**

> **Header:** "Next step"
> **Question:** "PDF + citation are in to_be_organized/. Summarize now, or leave the files for later?"
> **Options (single):** `Summarize now` / `Leave in to_be_organized/`
> **(batch):** `Summarize all now` / `Pick which` / `Leave all`

If **Leave** → stop; report the PDF path and `sidecar_path`. (The user can run
paper-organizer whenever.)

## If "Summarize now"

1. Pick engine + mode the same way `paper-organizer` does (don't re-implement —
   defer to its `SKILL.md` routing):
   - **engine** ∈ OpenRouter (default) / Agy CLI / Codex CLI / current-coding-agent. Ask only if the user didn't say.
   - **mode** ∈ full / metadata-only. Ask if not specified.
2. Invoke the **paper-organizer** skill on the downloaded PDF path(s). For the
   default OpenRouter engine that is, e.g.:

   ```bash
   cd paperhub_utils && uv run python -m scripts.paper_organizer "../to_be_organized/<stem>.pdf" --summary-mode full
   ```

3. **Do not pass `--instruction` for the citation** — `scripts.paper_organizer`
   auto-detects the same-stem `{stem}.citation.md` and folds it into the prompt as
   authoritative bibliographic context. (Still pass `--instruction` for any
   *additional* user ask like "focus on identification".)
4. The summarizer's own post-AI flow then validates, moves the PDF **and the
   sidecar** into `organized/<paper_label>/`, runs tags, and commits.

## Why this works without extra wiring

`scripts.paper_organizer` calls `fold_sidecar_into_instruction(pdf_path, …)` before
building the prompt (in both the OpenRouter path and the external-CLI prep), and
`organize_from_response` moves `{stem}.citation.md` into the paper folder
alongside the PDF. So the citation the finder wrote becomes both prompt context
and a permanent record next to the paper.
