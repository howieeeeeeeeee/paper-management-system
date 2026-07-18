---
name: ask-knowledge-base
description: Answer questions from this Obsidian vault's existing Markdown notes. Triggers when users ask "what do my notes say about...", "search my vault for...", "ask the knowledge base...", "do I have notes on...", or want a synthesis across non-hidden Markdown files in the vault. Expands the question into search terms, runs one bounded local `scripts.knowledge_base_search` call over visible Markdown files, reads only the returned context, and answers with Obsidian wikilinks. Add `--ignore-papers` when the user asks for vault notes but not paper metadata/summaries. NOT for finding a specific remembered paper already in `organized/` - use paper-finder for paper recall.
---

# Ask Knowledge Base

The project's root folder contains a `.claude` directory. Open `.claude/skills/ask-knowledge-base/SKILL.md` (from that root) for the canonical workflow and rules.

In brief: expand the user's question into 5-10 search terms, run **one** call to `cd paperhub_utils && uv run python -m scripts.knowledge_base_search` (`--terms ... --top 10 --detail 10` by default), and answer only from the returned digest with Obsidian wikilinks. When a matched note is a paper (metadata note or generated summary), its card carries a `journal=` line — mention the journal/conference alongside the citation. Format math with Obsidian-compatible `$...$` delimiters inline and `$$...$$` delimiters for display equations. Increase `--top`/`--detail` when the user asks for more sources. Add `--exclude` to penalize unwanted neighboring topics. Add `--ignore-papers` only when the user explicitly asks for vault notes but not paper metadata/summaries; it skips standard PaperHub `organized/<paper_label>/<paper_label>.md` metadata notes, `ai_summary.md` / `AI summary` Markdown files, and legacy `summary.md` paper summaries while keeping other hand-written Markdown notes. If the user asks for a detailed / comprehensive / in-depth answer, add `--full` and narrow `--detail` to 1-3 when possible. Never read the whole vault directly; the script searches visible Markdown files and skips dot-prefixed folders such as `.claude/`, `.agents/`, `.obsidian/`, `.git/`, and `.venv/`. Read-only: this skill never modifies notes, papers, tags, or config.

## Local uv environment

The virtual environment is disposable local state. In iCloud-synced vaults, do not try to preserve or share `.venv` across machines. Run commands from `paperhub_utils/`. If a normal `uv` command fails because the environment is stale or broken, first run:

```bash
uv sync
```

If that still fails, rebuild the local environment:

```bash
rm -rf .venv
uv sync
```

`pyproject.toml` and `uv.lock` are the source of truth; `.venv` can always be recreated on each computer. The search script needs only stdlib + pyyaml, so `python3 -m scripts.knowledge_base_search ...` also works as a fallback from `paperhub_utils/`.
