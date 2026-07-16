---
name: ask-knowledge-base
description: Answer questions from this Obsidian vault's existing Markdown notes. Triggers when users ask "what do my notes say about...", "search my vault for...", "ask the knowledge base...", "do I have notes on...", or want a synthesis across non-hidden Markdown files in the vault. Expands the question into search terms, runs one bounded local `scripts.knowledge_base_search` call over visible Markdown files, reads only the returned context, and answers with Obsidian wikilinks. Add `--ignore-papers` when the user asks for vault notes but not paper metadata/summaries. NOT for finding a specific remembered paper already in `organized/` - use paper-finder for paper recall.
---

# Ask Knowledge Base

Answer questions from visible Markdown files in the configured Obsidian vault. The vault can be much larger than the context window, so **never read the whole vault directly**. Use `paperhub_utils/scripts/knowledge_base_search.py` to rank notes and return bounded context; that output is your source material.

## Workflow

### 1. Expand the question

From the user's question, generate **5-10 search terms**: the user's own words, synonyms, likely note titles, project names, author names, concepts, method words, and exact phrases. Multi-word phrases are useful.

If the user says "not X", "excluding Y", or wants to steer away from a neighboring topic, generate 1-3 exclude terms for `--exclude`. Exclude terms are soft penalties, not hard filters.

### 2. One search call

Run from `paperhub_utils/`:

```bash
uv run python -m scripts.knowledge_base_search \
  --terms "moral wiggle room" "strategic ignorance" "dictator game" \
  --top 10 --detail 10
```

- Default to `--top 10 --detail 10`.
- If the user asks for more sources, increase `--top` and `--detail` to the requested count.
- The script searches Markdown files under `paperhub_utils/config/config.json`'s `obsidian.vault_abs_path` when valid; otherwise it falls back to the PaperHub root. It skips any path with a dot-prefixed segment such as `.claude/`, `.agents/`, `.obsidian/`, `.git/`, or `.venv/`.
- Cards include score, Obsidian wikilink, title, relative path, matched terms, and snippets. When the matched note is a paper (metadata note or generated summary), the card also carries a `journal=` line with the journal/conference from the paper's metadata.
- By default, PaperHub paper metadata notes and generated summaries are included. If the user explicitly asks for notes but not papers, says "without papers", "ignore papers", "non-paper notes", or similar, add `--ignore-papers`. That skips only standard PaperHub paper Markdown: `organized/<paper_label>/<paper_label>.md` metadata notes plus `ai_summary.md`, `AI summary`, and legacy `summary.md` files inside paper folders. Other Markdown notes, including hand-written notes inside `organized/<paper_label>/`, remain searchable.

Use `--exclude` for nearby topics the user does not want:

```bash
uv run python -m scripts.knowledge_base_search \
  --terms "belief updating" "good news bad news" \
  --exclude "survey" "teaching notes" \
  --top 10 --detail 10
```

Use `--ignore-papers` when the request is about non-paper notes:

```bash
uv run python -m scripts.knowledge_base_search \
  --terms "confirmation bias" "large language model" "LLM" \
  --top 10 --detail 10 --ignore-papers
```

Use `--full` only when the user asks for a detailed, comprehensive, or in-depth answer. Narrow the detailed set when possible:

```bash
uv run python -m scripts.knowledge_base_search \
  --terms "belief updating" "good news bad news" \
  --top 5 --detail 3 --full
```

### 3. Answer from the returned context

Write a direct answer to the user's question using only the search output. Cite the notes inline with the returned wikilinks, for example `[[projects/literature_map|Literature Map]]`. For standard paper metadata notes, the script returns compact links such as `[[danaetal2007moralwiggle]]`. When a cited source is a paper and its card carries a `journal=` line, mention the journal/conference alongside the citation.

Useful answer shapes:
- **Factual question:** concise answer first, then 2-4 cited supporting points.
- **Synthesis question:** group the answer by themes, tensions, or chronology; cite each theme.
- **Inventory question:** list the most relevant notes and why each matters.

If the evidence is weak or sparse, say so. Do not invent facts beyond the returned snippets/full context.

### 4. Iterate if weak

If the top matches are off-topic, scores look low, or the user says the answer missed the target:
- Try broader or alternate vocabulary.
- Drop terms that match too many unrelated notes.
- Add exclude terms for the unwanted cluster.
- Re-run up to about three quick rounds.

If the user is trying to remember a specific paper already in `organized/`, switch to `paper-finder`; it is better tuned for paper metadata and summaries.

## Critical rules

- **Read boundary:** do not recursively read vault Markdown files yourself. Use the script digest; only use `--full` for a narrow detailed set when the user asks for depth.
- **Answer boundary:** answer only from returned context and explicitly cite relevant notes with Obsidian wikilinks.
- **Search scope:** visible Markdown files only; dot-prefixed folders are skipped by the script. Use `--ignore-papers` only when the user asks to exclude paper metadata/summaries.
- **uv run location:** always run from `paperhub_utils/`.
- **Paths with spaces:** pass literal paths to file tools; only quote or escape paths inside shell commands.
- **Read-only skill:** never modify notes, paper folders, tags, or config from this skill.

## What this skill does NOT do

- Does NOT organize, summarize, or enrich PDFs - that is `paper-organizer`.
- Does NOT locate a half-remembered paper from `organized/` - that is `paper-finder`.
- Does NOT search the web.
