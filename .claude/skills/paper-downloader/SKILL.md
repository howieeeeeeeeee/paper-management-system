---
name: paper-downloader
description: Download and cite NEW research papers from the web, then hand off to paper-summarizer. Triggers when users want to fetch, download, get, pull, or grab a paper (or several) they do NOT yet have, by title/author, DOI, arXiv ID, or URL; resolve a citation/BibTeX; or process the "papers to find.md" backlog. Searches open-access APIs (arXiv/OpenAlex/Crossref/Unpaywall) and, for paywalled journals, drives the local gstack browser over the user's school VPN for legitimate institutional access. Real published version first, free working-paper version as fallback. Always writes a citation sidecar and offers to summarize. NOT for locating papers already in organized/ — that is the paper-finder skill.
---

# Research Paper Downloader

The front-end to `paper-summarizer`. Given paper info, this **resolves metadata → downloads a PDF into `to_be_organized/` → writes a `{stem}.citation.md` sidecar → offers to summarize**. The summarizer auto-detects that sidecar and uses it as authoritative context, so the citation flows through automatically.

**Read only the doc(s) you need** — this file routes; the details live in the sub-docs.

## File map

```
SKILL.md                       ← you are here (router only)
input_types/
  resolve_input.md             ← classify title/DOI/arXiv/URL/batch; expand wiki-link labels
modes/
  auto.md                      ← DEFAULT: real paper first (OA → ask → VPN), WP fallback
  open_access.md               ← API + working-paper only; never opens a browser
  browser.md                   ← gstack/VPN download of a paywalled real paper
  citation_only.md             ← metadata + sidecar only, no PDF
shared/
  fetcher_contract.md          ← the exact `scripts.paper_fetcher` CLI + JSON contract
  browser_download.md          ← gstack recipe, cookie-bridge, handoff/resume, ETHICS boundary
  handoff_to_summarizer.md     ← end-of-flow "summarize now?" + how to invoke paper-summarizer
```

## Core flow

1. **Classify the input and pick the mode.** If either is ambiguous, run the *Ask gate* below. Read `input_types/resolve_input.md` when the input form is unclear or it's a batch.
2. **Read the one mode doc** that matches and execute it. Every mode calls `scripts.paper_fetcher` (see `shared/fetcher_contract.md`) and writes a sidecar.
3. **Handoff.** After files land in `to_be_organized/`, read `shared/handoff_to_summarizer.md` and ask whether to summarize now.

## Routing — modes

| User says | Mode | Read |
|-----------|------|------|
| "find / get / download / fetch / grab X", or no mode given | `auto` (default) | `modes/auto.md` |
| "open access only" / "no VPN/browser" / "working paper is fine" | `open-access` | `modes/open_access.md` |
| "use the VPN" / "it's on JSTOR/ScienceDirect/Springer" / "behind a paywall" / "I have access through my school" | `browser` | `modes/browser.md` |
| "just the citation" / "bibtex only" / "I already have the PDF" / "add it to papers to find" | `citation-only` | `modes/citation_only.md` |

## Routing — input types

Classify by regex (details + normalization in `input_types/resolve_input.md`):

| Input | Detect | Fetcher arg |
|-------|--------|-------------|
| arXiv ID | `^(arXiv:)?\d{4}\.\d{4,5}(v\d+)?$` | `--arxiv <id>` |
| DOI | `^10\.\d{4,9}/\S+` (strip `https://doi.org/`) | `--doi <doi>` |
| Direct URL | `^https?://…` (not doi.org) | `--url <url>` |
| Title / author | free text with spaces | `--title "…" [--author "…"]` |
| Batch | "papers to find" / "the list" / a path to it | iterate `to_be_organized/papers to find.md` |

## Ask gate ("ask which mode and type if not specified")

Before doing any work, if the message does **not** clearly encode **both** a classifiable input **and** a mode keyword, call **AskUserQuestion** (one call, up to two questions):

- **Q1 — mode** (only if no mode keyword): `Auto (recommended)` / `Open-access only` / `Browser via school VPN` / `Citation only`.
- **Q2 — input type** (only if the regex cannot classify the input): `Title / author` / `DOI` / `arXiv ID` / `Direct URL` / `Batch from "papers to find.md"`.

Skip a question whenever it's already determined. If the user pasted a DOI and said "download it", skip both and go straight to `auto`.

## Critical rules (apply always)

- **uv run location:** always `cd paperhub_utils` before `uv run`, since `pyproject.toml` and `.venv` live there. Example: `cd paperhub_utils && uv run python -m scripts.paper_fetcher --arxiv 2504.09343`.
- **Paths with spaces:** pass literal paths (spaces as-is) to `Read`/`Edit`/`Write`; only backslash-escape inside Bash. The project root contains spaces.
- **The fetcher prints JSON to stdout, logs to stderr.** Parse stdout as JSON; never assume a field — read `shared/fetcher_contract.md` for the schema.
- **Real published version first.** The working-paper copy (NBER/SSRN/RePEc/author site) is a *fallback*; the sidecar always carries the latest published citation regardless of which PDF was obtained.
- **Browser = legitimate access only.** The gstack/VPN path is for open-access sources and for paywalled publishers reached through the user's own institutional entitlement. **Never** Sci-Hub / LibGen / paywall circumvention. If a paper is neither free nor institutionally accessible, stop at "sidecar written, PDF unavailable" and say so.
- **Confirm low-confidence matches.** For title search (especially batch), show the top candidate (title / authors / year) and confirm before downloading unless the user said "just grab them".
- **Never overwrite an existing PDF/sidecar** — the fetcher's `unique_stem` handles collisions; don't fight it.

## Quick start

```
"Find Coutts 2019 good news bad news belief updating"   → auto × title
"Download arxiv 2504.09343"                              → auto × arXiv
"Get me 10.1257/aer.20181169, it's on the AEA site"     → browser × DOI
"Just the bibtex for Melitz 2003 trade"                 → citation-only × title
"Work through papers to find.md, open access only"      → open-access × batch
```

## What this skill does NOT do

- Does NOT summarize or organize papers itself — it hands off to `paper-summarizer`.
- Does NOT circumvent paywalls — institutional/VPN and open-access only.
- Does NOT invent metadata — everything in the sidecar comes from a citation database (or is left blank for the summarizer to fill from the PDF).
