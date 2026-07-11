---
name: paper-organizer
description: Organize research papers from local PDFs or public paper links. Use for PaperHub onboarding, PDF metadata/full summaries, parallel mixed-link batches, link metadata and abstracts, batches from Markdown link lists, or enriching existing folders. Supports OpenRouter, Agy CLI, Codex CLI, and current-coding-agent engines while keeping external link-engine calls offline.
---

# Research Paper Organizer

The project's root folder contains a `.claude` directory. Open
`.claude/skills/paper-organizer/SKILL.md` from that root for the canonical router
and rules. Read only the engine, mode, link, tag, or onboarding playbooks it
selects.

Run `uv` commands from `paperhub_utils/`. The local `.venv` is disposable; use
`uv sync` if it is stale.
