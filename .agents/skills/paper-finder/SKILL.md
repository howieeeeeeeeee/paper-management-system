---
name: paper-finder
description: Locate papers ALREADY IN this library from a vague or partial memory. Triggers when the user half-remembers a paper and wants to know which one it is - "which paper was it that...", "I vaguely remember a paper about...", "can't remember the paper that showed...", "do I already have a paper on...", or "search/find in my library", including "but not the X ones" to steer away from a neighboring literature. Searches every visible Markdown note inside each valid paper folder, aggregates matches by paper label, and presents metadata, AI-summary, and matched-note evidence. NOT for downloading new papers (paper-downloader) or organizing/summarizing them (paper-organizer).
---

# Paper Finder (library recall)

The project's root folder contains a `.claude` directory. Open `.claude/skills/paper-finder/SKILL.md` (from that root) for the canonical workflow and rules.

In brief: expand the user's vague memory into 5-10 search terms, run **one** call to `cd paperhub_utils && uv run python -m scripts.paper_search` (`--terms ... --top 15 --detail 5`), and present paper-level candidates with `[[label]]` wikilinks. The script searches all visible Markdown recursively inside each valid paper folder, returning trimmed metadata, AI-summary context, and matched-note paths/excerpts; cards show the journal/conference next to the year when the metadata records one — always report it. Use `--exclude` for soft negative terms. For a **detailed / comprehensive / in-depth** look, add `--full` and narrow `--detail` to 1-3; full output includes complete metadata, complete `ai_summary.md`, and matched extra notes only, with `--max-extra-full-chars 60000` by default (`0` is unbounded). Never Read candidate folders wholesale; use the script output as context. Read-only: never modify paper folders or tags.

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

`pyproject.toml` and `uv.lock` are the source of truth; `.venv` can always be recreated on each computer. The search script needs only stdlib + pyyaml, so `python3 -m scripts.paper_search ...` also works as a fallback from `paperhub_utils/`.
