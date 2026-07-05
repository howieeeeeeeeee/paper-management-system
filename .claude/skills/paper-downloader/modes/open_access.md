# Mode: open-access

Goal: get a **free** PDF only — never open a browser, never touch the VPN. Tries
the publisher open-access copy first, then a working-paper version
(NBER/SSRN/RePEc/author site, surfaced via Unpaywall green OA + OpenAlex
repository locations).

## Steps

1. Run the fetcher:

   ```bash
   cd paperhub_utils && uv run python -m scripts.paper_fetcher <source> --mode open-access
   ```

2. Parse the JSON:

   - **`downloaded_path` set** → free PDF is in `to_be_organized/`. Note `metadata.version` (`published` if the OA publisher copy, `working_paper` if a repository copy). Report it, then go to **handoff** (`shared/handoff_to_summarizer.md`).
   - **`downloaded_path` null** → no free PDF exists. The sidecar is written. Tell the user the published copy looks paywalled and offer to re-run in `auto`/`browser` mode to fetch it through their VPN. Do **not** open a browser here.

## When to use

- The user said "open access only", "no VPN/browser", or "a working paper is fine".
- Quick, safe batch passes over `papers to find.md` where you don't want login prompts.

## Working-paper search fallback (if the APIs found nothing)

If the fetcher returned no `wp_pdf_url` but you suspect a free copy exists (common
for econ), you may use **WebSearch/WebFetch** to look for one — e.g. search
`"<title>" <author> filetype:pdf` and check NBER / SSRN / RePEc-IDEAS / the
author's homepage. **Validate it's a real PDF** before saving (the bytes start
with `%PDF`), then download it to `to_be_organized/<stem>.pdf` (reuse the sidecar
stem) via:

```bash
cd paperhub_utils && uv run python -m scripts.paper_fetcher --url "<pdf_url>" --mode open-access --stem <stem>
```

Never use Sci-Hub/LibGen. If nothing legitimate turns up, stop at the sidecar.
