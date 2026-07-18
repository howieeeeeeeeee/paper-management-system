---
name: paper-finder
description: Locate papers ALREADY IN this library from a vague or partial memory. Triggers when the user half-remembers a paper and wants to know which one it is - "which paper was it that...", "I vaguely remember a paper about...", "can't remember the paper that showed...", "do I already have a paper on...", or "search/find in my library", including "but not the X ones" to steer away from a neighboring literature. Searches every visible Markdown note inside each valid paper folder, aggregates matches by paper label, and presents metadata, AI-summary, and matched-note evidence. NOT for downloading new papers (paper-downloader) or organizing/summarizing them (paper-organizer).
---

# Paper Finder (library recall)

Turn a fuzzy memory ("that one about ignoring information in a dictator game...?") into a ranked list of candidate papers from `organized/`. Search every visible Markdown file recursively within each valid paper folder, but aggregate all evidence into one result for that paper label. The library is too large to read directly, so **never Read candidate folders wholesale** — use the bounded context returned by `paperhub_utils/scripts/paper_search.py`.

## Workflow

### 1. Expand the query

From the user's description, generate **5–10 search terms**: the words they used, synonyms, method words ("dictator game", "RCT", "structural"), likely author surnames, result phrases, and plausible canonical tags. Multi-word phrases are fine (the script matches them exactly, case-insensitive). If unsure which tags exist, skim `tags/tags_summary.md` — but only when topic words feel off.

Term quality notes:
- The scorer rewards **distinct-term coverage** over repetition — a few diverse, specific terms beat many near-duplicates.
- Avoid ultra-generic terms ("model", "experiment", "economics") — they match half the library and dilute ranking.
- **Exclude terms:** when the user wants to steer *away* from something ("but not the survey ones", "not the field-experiment stuff"), also generate 1–3 exclude keywords for `--exclude`. These deduct score rather than hard-filter, so a strong match still surfaces if it genuinely fits.

### 2. One search call

```bash
cd paperhub_utils && uv run python -m scripts.paper_search \
  --terms "moral wiggle room" "dictator game" "self-image" "Dana" \
  --top 15 --detail 5
```

- `--top 15 --detail 5` is the default presentation: 5 full cards + 10 brief lines (~1.5–2K tokens).
- Scoring: field-weighted term hits (title 3.0, tags/authors 2.5, abstract 1.5, metadata body 1.0, ai_summary body 0.5, all additional Markdown aggregated as one 1.0 field), per-field count caps, and a distinct-term coverage bonus. Repeated copies across many notes cannot create independent field bonuses.
- Normal cards provide trimmed metadata and AI-summary context plus query-centered excerpts and relative paths for every matched additional note. A note match contributes to its parent paper; it is never a separate candidate.
- **Optional `--exclude`** (space-separated, quote phrases) penalizes unwanted keywords — hits are *subtracted* at 2× the field weights (same per-field cap). It's a soft deduct, not a hard filter: a paper drops off only when the penalty outweighs its include matches. Use it to separate two close literatures:

```bash
cd paperhub_utils && uv run python -m scripts.paper_search \
  --terms "correlation neglect" "belief updating" \
  --exclude "survey" "field experiment" \
  --top 15 --detail 5
```

- **Detailed mode `--full`** (off by default) — turn it on when the user asks for a "detailed", "comprehensive", "in-depth", or "deep" look. Each detailed-rank card returns the complete metadata note, complete `ai_summary.md`, and complete matched additional notes. It never returns unmatched extra notes. Additional-note text is capped at 60,000 characters per paper by default; adjust `--max-extra-full-chars`, or use `0` explicitly for unbounded output. Narrow `--detail` to 1–3:

```bash
cd paperhub_utils && uv run python -m scripts.paper_search \
  --terms "correlation neglect" "belief updating" \
  --top 5 --detail 2 --full --max-extra-full-chars 60000
```

### 3. Present the candidates

Show a ranked list in chat:
- **Top matches (up to 5):** for each — `[[label]]`, title, authors (year, journal/conference — the card's venue is shown next to the year when the metadata records one; always report it), status/interest, tags, and a one-line **"why it matches"** tying the user's memory to the digest evidence. Mention matched additional-note paths when they supply the relevant evidence, but keep the paper as the result.
- **Other candidates:** the brief tail as one line each (`[[label]]` — title, year).

Format mathematical expressions with Obsidian-compatible LaTeX delimiters: use `$...$` for inline math and `$$...$$` for display equations.

Do not pad: if only 2 papers plausibly match, show 2 detailed and say so.

**Detailed mode:** when you ran with `--full`, write a comprehensive synthesis from the complete metadata, AI summary, and matched additional notes returned by the script. Distinguish the canonical paper record from personal lecture, presentation, model, or experiment notes when attributing evidence.

### 4. Iterate if weak

If top scores are low, results look off-topic, or the user says "none of these":
- Swap in broader/alternative vocabulary (different literature's phrasing, English vs. jargon variants), drop terms that matched everything, re-run. Up to ~3 rounds — each is <1s and cheap.
- If the user remembers an **exact phrase** (a quote, a payoff like "$6", a dataset name), first retry it as a quoted search term. If a literal fallback is still necessary, use `rg -il --glob '*.md' "<phrase>" organized/` and map paths back to paper labels; do not read every returned file.

### 5. On a pick

When the user identifies the paper, offer to open its metadata note, `ai_summary.md`, and any matched additional note, or hand off ("enrich <label>" → paper-organizer).

## Critical rules

- **Paths with spaces:** pass literal paths (spaces as-is) to `Read`/`Edit`/`Write`; backslash-escape only inside Bash commands. The project root contains spaces.
- **uv run location:** always `cd paperhub_utils` before `uv run` (that's where `pyproject.toml` and `.venv` live). If uv is stale/broken: `uv sync`; if that fails, `rm -rf .venv && uv sync`. The script needs only stdlib + pyyaml, so `python3 -m scripts.paper_search ...` also works as a fallback.
- **Token budget:** rely on the script digest and keep each normal search round near 4K tokens. Only Read files directly after the user picks a paper. Detailed mode `--full` is the deliberate exception and must use a narrow `--detail` set.
- **Read-only skill:** never modify paper folders, metadata, or tags here.

## What this skill does NOT do

- Does NOT download or fetch new papers — that is `paper-downloader`.
- Does NOT summarize, organize, or enrich — that is `paper-organizer`.
- Does NOT search the web; it only searches `organized/`.
