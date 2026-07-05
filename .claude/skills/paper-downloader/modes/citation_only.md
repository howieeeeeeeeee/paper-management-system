# Mode: citation-only

Goal: resolve and write the `{stem}.citation.md` sidecar — title, authors, year,
journal, DOI, abstract, BibTeX — without downloading any PDF.

Use when the user wants just a citation/BibTeX, already has the PDF, or is
building the `papers to find.md` backlog.

## Steps

1. Run the fetcher:

   ```bash
   cd paperhub_utils && uv run python -m scripts.paper_fetcher <source> --citation-only
   ```

2. Report `sidecar_path` and the resolved title/authors/year. Offer the BibTeX
   (it's in the sidecar's `## BibTeX` block). No summarizer handoff — there is no
   PDF.

## Optional: pairing with a PDF the user already has

If the user already dropped a PDF into `to_be_organized/`, pass `--stem` so the
sidecar pairs with it (same stem as the PDF, minus `.pdf`):

```bash
cd paperhub_utils && uv run python -m scripts.paper_fetcher <source> --citation-only --stem <pdf_stem>
```

Then the summarizer will pick the citation up automatically when it processes
that PDF.

## Optional: updating `papers to find.md`

If the user asks to add/annotate an entry in `to_be_organized/papers to find.md`,
that's a user document — **ask before editing it**. Entries follow
`- [[label]] - reason.` (the label is `surname+year+topicword`).
