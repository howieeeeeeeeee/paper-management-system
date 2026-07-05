---
name: paper-finder
description: Locate papers ALREADY IN this library from a vague or partial memory. Triggers when the user half-remembers a paper and wants to know which one it is - "which paper was it that...", "I vaguely remember a paper about...", "can't remember the paper that showed...", "do I already have a paper on...", "search/find in my library", including "but not the X ones" to steer away from a neighboring literature. Expands the description into search terms (and optional exclude keywords that deduct score), runs one paper_search.py call over organized/, and presents a ranked candidate list with metadata labels and summary snippets. NOT for downloading new papers (paper-downloader) and NOT for summarizing (paper-summarizer).
---

# Paper Finder (library recall)

Turns a fuzzy memory ("that one about ignoring information in a dictator game...?") into a ranked list of candidate papers from `organized/`. The library is far too large to read directly (~6 MB of notes), so **never Read candidate files wholesale** — `paperhub_utils/paper_search.py` does the filtering and returns a token-bounded digest; that digest is your context.

## Workflow

### 1. Expand the query

From the user's description, generate **5–10 search terms**: the words they used, synonyms, method words ("dictator game", "RCT", "structural"), likely author surnames, result phrases, and plausible canonical tags. Multi-word phrases are fine (the script matches them exactly, case-insensitive). If unsure which tags exist, skim `tags/tags_summary.md` — but only when topic words feel off.

Term quality notes:
- The scorer rewards **distinct-term coverage** over repetition — a few diverse, specific terms beat many near-duplicates.
- Avoid ultra-generic terms ("model", "experiment", "economics") — they match half the library and dilute ranking.
- **Exclude terms:** when the user wants to steer *away* from something ("but not the survey ones", "not the field-experiment stuff"), also generate 1–3 exclude keywords for `--exclude`. These deduct score rather than hard-filter, so a strong match still surfaces if it genuinely fits.

### 2. One search call

```bash
cd paperhub_utils && uv run python paper_search.py \
  --terms "moral wiggle room" "dictator game" "self-image" "Dana" \
  --top 15 --detail 5
```

- `--top 15 --detail 5` is the default presentation: 5 full cards + 10 brief lines (~1.5–2K tokens).
- Scoring: field-weighted term hits (title 3.0, tags/authors 2.5, abstract 1.5, metadata body 1.0, ai_summary body 0.5), per-field count cap, plus a distinct-term coverage bonus. Cards show label, title, authors/year/journal, status/interest/importance, tags, abstract (~80 words), and ai_summary opening (~100 words).
- **Optional `--exclude`** (space-separated, quote phrases) penalizes unwanted keywords — hits are *subtracted* at 2× the field weights (same per-field cap). It's a soft deduct, not a hard filter: a paper drops off only when the penalty outweighs its include matches. Use it to separate two close literatures:

```bash
cd paperhub_utils && uv run python paper_search.py \
  --terms "correlation neglect" "belief updating" \
  --exclude "survey" "field experiment" \
  --top 15 --detail 5
```

- **Detailed mode `--full`** (off by default) — turn it on when the user asks for a "detailed", "comprehensive", "in-depth", or "deep" look. Each detailed-rank card then dumps the paper's *entire* metadata note (all sections: reflections, key takeaways, related-paper links) and *full* ai_summary instead of the truncated snippets. It intentionally blows past the usual token budget, so **narrow `--detail` to 1–3** (and usually a smaller `--top`):

```bash
cd paperhub_utils && uv run python paper_search.py \
  --terms "correlation neglect" "belief updating" \
  --top 5 --detail 2 --full
```

### 3. Present the candidates

Show a ranked list in chat:
- **Top matches (up to 5):** for each — `[[label]]`, title, authors (year, journal), status/interest, tags, and a one-line **"why it matches"** tying the user's memory to the digest evidence. Quote the abstract/summary snippet only where it helps.
- **Other candidates:** the brief tail as one line each (`[[label]]` — title, year).

Do not pad: if only 2 papers plausibly match, show 2 detailed and say so.

**Detailed mode:** when you ran with `--full`, don't compress to one-liners — write a comprehensive, structured synthesis of each detailed paper (research question, method, key findings, and relevance/links) drawn from the full metadata note and ai_summary the script returned.

### 4. Iterate if weak

If top scores are low, results look off-topic, or the user says "none of these":
- Swap in broader/alternative vocabulary (different literature's phrasing, English vs. jargon variants), drop terms that matched everything, re-run. Up to ~3 rounds — each is <1s and cheap.
- If the user remembers an **exact phrase** (a quote, a payoff like "$6", a dataset name), fall back to `grep -ril "<phrase>" organized/` and map hits back to folder labels.

### 5. On a pick

When the user identifies the paper, offer to open its full metadata note (`organized/<label>/<label>.md`) and/or `ai_summary.md`, or hand off ("enrich <label>" → paper-summarizer).

## Critical rules

- **Paths with spaces:** pass literal paths (spaces as-is) to `Read`/`Edit`/`Write`; backslash-escape only inside Bash commands. The project root contains spaces.
- **uv run location:** always `cd paperhub_utils` before `uv run` (that's where `pyproject.toml` and `.venv` live). If uv is stale/broken: `uv sync`; if that fails, `rm -rf .venv && uv sync`. The script needs only stdlib + pyyaml, so `python3 paper_search.py ...` also works as a fallback.
- **Token budget:** rely on the script digest; keep each search round's chat output ≤ ~4K tokens. Only Read a paper's full files after the user picks it. (Detailed mode `--full` is the deliberate exception — it returns full notes for a narrow `--detail` set so you can synthesize deeply.)
- **Read-only skill:** never modify paper folders, metadata, or tags here.

## What this skill does NOT do

- Does NOT download or fetch new papers — that is `paper-downloader`.
- Does NOT summarize, organize, or enrich — that is `paper-summarizer`.
- Does NOT search the web; it only searches `organized/`.
