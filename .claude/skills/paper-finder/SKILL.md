---
name: paper-finder
description: Locate papers ALREADY IN this library from a vague or partial memory. Triggers when the user half-remembers a paper and wants to know which one it is - "which paper was it that...", "I vaguely remember a paper about...", "can't remember the paper that showed...", "do I already have a paper on...", or "search/find in my library", including "but not the X ones" to steer away from a neighboring literature. Searches every visible Markdown note inside each valid paper folder, aggregates matches by paper label, and presents metadata, AI-summary, and matched-note evidence. NOT for acquiring new papers or organizing/summarizing them (paper-organizer).
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

#### Specific-but-fuzzy memories: use a claim-first keyword ladder

When the user remembers a fairly specific result or mechanism but not the citation, do not flatten
the memory into broad topic words. Decompose it into independently searchable dimensions:

1. **Object or population:** who or what was studied ("LLMs", "investors", "children").
2. **Task or mechanism:** what they did ("Bayesian updating", "forecasting", "dictator game").
3. **Comparison:** what varied ("newer versus older", "large versus small", treatment versus control).
4. **Direction of the result:** what changed ("more rational", "less biased", "ignored information").
5. **Benchmark or design language:** likely task names, canonical biases, datasets, or methods
   ("base-rate neglect", "AR(1)", "multiple price list").

Start with one or two terms from each remembered dimension. Preserve the user's distinctive
comparison and directional claim; those often identify the paper better than the broad topic.
Do not guess an author unless the user has some author memory.

Treat the first results as a **diagnostic vocabulary probe**, not automatically as the answer.
If high-ranked papers contain generic tokens such as "belief", "model", or "Bayesian" but do not
state the remembered comparison or finding, that is a vocabulary collision. Refine the next round
using the field's more discriminating language found in the candidate cards:

- replace loose words with canonical phrases ("calculation" → "base-rate neglect",
  "Bayes rule", "numerical reasoning");
- add the comparison axis ("model scale", "advanced versus older", "large versus smaller");
- add the outcome classification ("rational responses", "belief tasks", "human-like");
- after a plausible candidate appears, use a distinctive title fragment or result phrase to
  separate it from neighboring papers and earlier/later versions.

For example, a memory like "newer or larger models were better at calculation and Bayesian
updating" can progress from:

- broad anchors: `"Bayesian updating"`, `"belief updating"`, `"larger models"`,
  `"newer models"`, `"numerical reasoning"`, `"large language models"`;
- diagnostic refinement: `"Bayes rule"`, `"base-rate neglect"`, `"belief tasks"`,
  `"model scale"`, `"advanced versus older"`, `"large versus smaller"`;
- candidate confirmation: a distinctive title fragment plus `"probabilistic beliefs"` or the
  exact comparison/result language shown in the leading cards.

This ladder is still one search call per round. Use at most about three rounds, changing the
vocabulary materially each time rather than repeatedly submitting near-duplicates.

### 2. One search call per round

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

- **Detailed mode `--full`** (off by default) — turn it on when the user asks for a "detailed", "comprehensive", "in-depth", or "deep" look. Also prefer it when the user remembers a specific empirical result, mechanism, or comparison but cannot recall the paper: complete summaries are often needed to verify the claim rather than merely match the topic. Each detailed-rank card returns the complete metadata note, complete `ai_summary.md`, and complete matched additional notes. It never returns unmatched extra notes. Additional-note text is capped at 60,000 characters per paper by default; adjust `--max-extra-full-chars`, or use `0` explicitly for unbounded output. Narrow `--detail` to 1–3:

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

If top scores are low, results look off-topic, the cards match only generic vocabulary, or the user says "none of these":
- Compare the leading cards against the remembered **task, comparison, and direction of result**.
  A high score is not persuasive when those dimensions are absent.
- Swap in broader/alternative vocabulary (different literature's phrasing, English vs. jargon
  variants), then narrow with discriminating phrases from the returned cards. Drop terms that
  matched everything. Re-run up to ~3 rounds; each round should represent a real hypothesis about
  how the target literature names the remembered idea.
- When two nearby papers remain, run the final round as a candidate comparison: include a
  distinctive phrase from each candidate plus the remembered result. Report the best match and
  explain why the close alternative is weaker.
- If the user remembers an **exact phrase** (a quote, a payoff like "$6", a dataset name), first retry it as a quoted search term. If a literal fallback is still necessary, use `rg -il --glob '*.md' "<phrase>" organized/` and map paths back to paper labels; do not read every returned file.

### 5. On a pick

When the user identifies the paper, offer to open its metadata note, `ai_summary.md`, and any matched additional note, or hand off ("enrich <label>" → paper-organizer).

## Critical rules

- **Paths with spaces:** pass literal paths (spaces as-is) to `Read`/`Edit`/`Write`; backslash-escape only inside Bash commands. The project root contains spaces.
- **uv run location:** always `cd paperhub_utils` before `uv run` (that's where `pyproject.toml` and `.venv` live). If uv is stale/broken: `uv sync`; if that fails, `rm -rf .venv && uv sync`. The script needs only stdlib + pyyaml, so `python3 -m scripts.paper_search ...` also works as a fallback.
- **Token budget:** rely on the script digest and keep each normal search round near 4K tokens. Only Read files directly after the user picks a paper. Detailed mode `--full` is the deliberate exception and must use a narrow `--detail` set.
- **Read-only skill:** never modify paper folders, metadata, or tags here.

## What this skill does NOT do

- Does NOT download or fetch new papers.
- Does NOT summarize, organize, or enrich — that is `paper-organizer`.
- Does NOT search the web; it only searches `organized/`.
