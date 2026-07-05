---
name: paper-summarizer
description: Automated research paper organization using AI. Triggers when users upload PDFs and ask to summarize, organize, or add papers to their library, or when they ask to enrich an existing folder with an AI summary. Supports OpenRouter, Agy CLI, Codex CLI, and current-coding-agent engines across full / metadata-only / enrich modes.
---

# Research Paper Summarizer

The project’s root folder contains a `.claude` directory. Open `.claude/skills/paper-summarizer/SKILL.md` (from that root) for the canonical workflow and rules.

Routes the user's request to the right `engine × mode`, then delegates to a per-doc playbook. **Read only the doc(s) you need** — don't load unrelated ones. For routine runs, **do not read** `paperhub_utils/*.py`; execute what the canonical skill and linked engine/mode docs specify. **Always provide an end-of-batch summary** per canonical `shared/post_ai.md` step 5 Report (and `modes/{mode}.md` templates) — see canonical `SKILL.md` Critical rules and Post-AI flow.

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

`pyproject.toml` and `uv.lock` are the source of truth; `.venv` can always be recreated on each computer.
