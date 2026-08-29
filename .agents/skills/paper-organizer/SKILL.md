---
name: paper-organizer
description: Organize research papers from local PDFs or public paper links. Use for PaperHub onboarding, PDF metadata/full summaries, parallel mixed-link batches, link metadata and abstracts, batches from Markdown link lists, or enriching existing folders. Supports OpenRouter, Agy CLI, Codex CLI, and current-coding-agent engines while keeping external link-engine calls offline.
---

# Research Paper Organizer

The project's root folder contains a `.claude` directory. Open
`.claude/skills/paper-organizer/SKILL.md` from that root for the canonical router
and rules. Read only the engine, mode, link, tag, or onboarding playbooks it
selects.

Before suggesting or invoking an engine, scan the user's request for a named
engine (codex, agy/antigravity, openrouter, gemini, or the current agent). A
named engine is binding and outranks every default; when no engine is named,
default to the current coding agent. Only then follow the canonical skill's
engine availability gate, which verifies a choice but never makes one. External
engines must appear in `config.json`'s `available_engines`; verify an explicitly
requested unlisted engine and append it only after the check or first run
succeeds. The current coding agent is always available.

If the chosen engine fails, stop and ask whether to retry, switch to a named
enabled engine, or abandon the paper. Never fall back to another engine or model
on your own.

Run `uv` commands from `paperhub_utils/`. The local `.venv` is disposable; use
`uv sync` if it is stale.
