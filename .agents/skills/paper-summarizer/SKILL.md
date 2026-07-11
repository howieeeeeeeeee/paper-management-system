---
name: paper-summarizer
description: Deprecated compatibility alias for PaperHub paper organization. Use when an existing prompt names paper-summarizer, then route the complete request to paper-organizer.
---

# Paper Summarizer Compatibility Alias

The project's root folder contains a `.claude` directory. Open
`.claude/skills/paper-organizer/SKILL.md` from that root and follow the canonical
workflow without changing the user's requested inputs, mode, engine, or extra
instructions.

Mention the new `paper-organizer` name in the completion report, but do not
block the legacy request or require migration.

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
