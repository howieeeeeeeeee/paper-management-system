# Fetcher contract — `scripts.paper_fetcher`

The deterministic helper. It resolves metadata via free APIs, downloads an
available PDF, and writes a `{stem}.citation.md` sidecar. It does **no** browser
automation — for paywalled journals it sets `needs_browser_fallback` and a
`browser_hint`, and the skill drives the browser (see `browser_download.md`).

## How to call

Always from `paperhub_utils/` (so `uv` finds `.venv`):

```bash
cd paperhub_utils && uv run python -m scripts.paper_fetcher <one source> [options]
```

**Source (exactly one, required):**

| Flag | Example |
|------|---------|
| `--title` | `--title "Good news and bad news are still news" --author Coutts` |
| `--doi` | `--doi 10.1007/s10683-018-9572-5` |
| `--arxiv` | `--arxiv 2504.09343` (or `2504.09343v1`) |
| `--url` | `--url "https://link.springer.com/content/pdf/....pdf"` |

**Options:**

| Flag | Meaning |
|------|---------|
| `--mode {auto,open-access,citation-only}` | default `auto`. `auto` downloads the publisher OA PDF if free, else flags the browser path. `open-access` also auto-grabs a working-paper copy. `citation-only` writes the sidecar only. |
| `--citation-only` | alias for `--mode citation-only` |
| `--author`, `--year` | disambiguation hints for `--title` |
| `--out-dir PATH` | defaults to `config.TO_BE_ORGANIZED_DIR` (i.e. `to_be_organized/`) — usually omit |
| `--stem STEM` | force the output filename stem (used by the browser bridge to keep PDF+sidecar paired) |
| `--cookies FILE` | JSON cookie jar for the VPN/browser bridge download |
| `--email EMAIL` | polite-pool contact (defaults to the configured email or `PAPERHUB_CONTACT_EMAIL`) |
| `--verbose` | INFO logs to stderr |

## Output — a single JSON object on stdout

```json
{
  "success": true,
  "input": {"kind": "arxiv|doi|url|title", "value": "..."},
  "mode": "auto",
  "metadata": {
    "title": "...", "authors": ["..."], "year": 2019, "journal": "...",
    "doi": "10....", "arxiv_id": "...", "abstract": "...",
    "url": "https://...", "source": "openalex|crossref|arxiv|url",
    "version": "published|working_paper"
  },
  "chosen_source": "crossref",
  "oa_pdf_url": "…|null",          // publisher / open-access "real paper" PDF
  "wp_pdf_url": "…|null",          // repository / working-paper PDF
  "downloaded_path": "/abs/to_be_organized/coutts2019good.pdf | null",
  "sidecar_path": "/abs/to_be_organized/coutts2019good.citation.md",
  "needs_browser_fallback": false,
  "browser_hint": {"landing_url": "https://doi.org/10....", "publisher": "elsevier|jstor|springer|null", "wp_pdf_url": "…|null"},
  "warnings": [], "errors": []
}
```

## How to read the result

- **`downloaded_path` non-null** → a PDF is in `to_be_organized/`. Done; go to handoff.
- **`downloaded_path` null + `needs_browser_fallback` true** → no free PDF; the real paper is likely paywalled. In `auto`, ask before the browser path (`modes/auto.md`).
- **`downloaded_path` null + `needs_browser_fallback` false** → no PDF and no browser warranted (or `open-access`/`citation-only`). The sidecar is still written; report it.
- **`sidecar_path`** is essentially always written — report it to the user even on partial failure.
- **`warnings`/`errors`** — surface these; e.g. a failed OA download attempt or a low-confidence title match.

stderr is logs only (it does not affect the JSON). Parse stdout with a small `python -c "import json,sys; d=json.load(sys.stdin); ..."` or read it directly.
