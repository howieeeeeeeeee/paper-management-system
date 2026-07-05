---
name: paper-finder
description: Locate papers ALREADY IN this library from a vague or partial memory. Triggers when the user half-remembers a paper and wants to know which one it is - "which paper was it that...", "I vaguely remember a paper about...", "can't remember the paper that showed...", "do I already have a paper on...", "search/find in my library", including "but not the X ones" to steer away from a neighboring literature. Expands the description into search terms (and optional exclude keywords that deduct score), runs one paper_search.py call over organized/, and presents a ranked candidate list with metadata labels and summary snippets. NOT for downloading new papers (paper-downloader) and NOT for summarizing (paper-summarizer).
---

# Paper Finder (library recall)

The project's root folder contains a `.claude` directory. Open `.claude/skills/paper-finder/SKILL.md` (from that root) for the canonical workflow and rules.

In brief: expand the user's vague memory into 5–10 search terms, run **one** call to `paperhub_utils/paper_search.py` (`--terms ... --top 15 --detail 5`), and present the ranked digest — 5 detailed cards with `[[label]]` wikilinks plus a brief tail. When the user wants to steer *away* from a neighboring literature ("but not the survey ones"), add the optional `--exclude "..." "..."` flag — those keywords deduct score (2× the field weights, soft penalty, not a hard filter). Never Read candidate files wholesale; the script's digest is the context. Read-only: this skill never modifies paper folders or tags.

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

`pyproject.toml` and `uv.lock` are the source of truth; `.venv` can always be recreated on each computer. The search script needs only stdlib + pyyaml, so `python3 paper_search.py ...` also works as a fallback.
