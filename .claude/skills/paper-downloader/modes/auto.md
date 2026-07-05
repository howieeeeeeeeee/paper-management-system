# Mode: auto (default)

Goal: get the **real published paper** if reasonably possible; fall back to a
free **working-paper** copy; always write the citation sidecar.

## Steps

1. **Resolve + try the open-access real paper.** Run the fetcher (see `shared/fetcher_contract.md`):

   ```bash
   cd paperhub_utils && uv run python paper_fetcher.py <source> --mode auto
   ```

   Parse the JSON from stdout.

2. **Branch on the result:**

   - **`downloaded_path` is set** → the open-access publisher PDF is in `to_be_organized/`. Report title/authors/year + the file, then go to **handoff**.

   - **`downloaded_path` is null and `needs_browser_fallback` is true** → the real paper is likely paywalled. The sidecar is already written. **AskUserQuestion:**

     > **Header:** "Paywalled"
     > **Question:** "No free copy of the published version. Fetch the real journal PDF via your school VPN (browser), use a free working-paper version instead, or stop with just the citation?"
     > **Options:** `Browser via VPN (real paper)` / `Working-paper version` / `Just the citation`

     - **Browser via VPN** → read `shared/browser_download.md` and drive gstack to download the real paper to `to_be_organized/<stem>.pdf` (reuse the same `stem` from `sidecar_path`). On success → handoff. On failure (no access / blocked) → offer the working-paper fallback, then citation-only.
     - **Working-paper version** → if `browser_hint.wp_pdf_url` (or `wp_pdf_url`) is set, re-run the fetcher in open-access mode to grab it and keep the published citation:
       ```bash
       cd paperhub_utils && uv run python paper_fetcher.py <same source> --mode open-access --stem <stem>
       ```
       Then handoff. If no `wp_pdf_url`, say so and fall to citation-only.
     - **Just the citation** → nothing more to download; report `sidecar_path`. (No summarizer handoff — there's no PDF.)

   - **`downloaded_path` null and `needs_browser_fallback` false** → no PDF and no useful browser target (e.g. a bare title that resolved but has no DOI). Report the sidecar and suggest re-running with a DOI/arXiv ID or in `browser` mode.

3. **Handoff.** Whenever a PDF landed, read `shared/handoff_to_summarizer.md`.

## Notes

- Keep the `stem` consistent between the citation-only/auto call and any later browser/working-paper download, so the PDF and `{stem}.citation.md` stay paired. The fetcher reports it in `sidecar_path` (strip the `.citation.md`).
- For a title input, if the fetcher logged a low-confidence match (a `warnings` entry, or the returned title looks wrong), confirm with the user before downloading.
- Batch (from `papers to find.md`): run this flow per item, but collect the paywalled ones and ask **once** at the end whether to do a VPN pass over all of them, rather than interrupting each time.
