---
name: paper-summarizer
description: Automated research paper organization using AI. Triggers when users ask to onboard, set up, configure, or first-run this paper library; when users upload PDFs and ask to summarize, organize, or add papers to their library; or when they ask to enrich an existing folder with an AI summary. Supports OpenRouter, Gemini CLI, and current-coding-agent engines across full / metadata-only / enrich modes.
---

# Research Paper Summarizer

Routes the user's request to the right `engine × mode`, then delegates to a per-doc playbook. **Read only the doc(s) you need** — don't load unrelated ones.

## File map

```
SKILL.md                  ← you are here (router only)
onboard.md                ← questionnaire-first setup inside an Obsidian vault
engines/
  openrouter.md           ← default; uses paper_summarizer.py via OpenRouter API
  gemini_cli.md           ← prepare/from-response handshake against `gemini` CLI
  coding_agent.md         ← in-process; full / metadata-only / enrich (high quota for full+enrich)
modes/
  full.md                 ← writes {paper_label}.md + ai_summary.md
  metadata_only.md        ← writes {paper_label}.md only (sends first N pages)
  enrich.md               ← writes ai_summary.md for an EXISTING folder; patches blank meta
shared/
  post_ai.md              ← validation, autofix, git, tag handoff, partial-failure handling
setup/
  python_uv_recovery.md   ← read only if uv is missing and pip cannot install it
tags/
  initialize_tag_system.md ← onboarding-only initial tag registry setup
  post_summary_update.md  ← post-batch tag registration and merge handoff
  periodic_check.md       ← user-triggered periodic tag normalization
```

## Command Preference

1. Default to one command per Bash call.
2. Combine only when the second command genuinely depends on the first's exit (mkdir -p X && touch X/y) or shares working state (cd X && uv sync).
3. Avoid cmd1 && cmd2 && echo DONE && wc -c file-style "status reports" — just run the command, then a separate read.
4. Prefer dedicated tools (Read, Edit, Write) over Bash where possible — those have their own simpler permission model.

## Routing

For onboarding/setup/first-run requests, read `onboard.md` and execute it before any paper-processing mode. Onboarding is questionnaire-first: if root `onboarding_questionnaire.md` exists, `onboard.md` tells the agent to read it before asking follow-up questions.

For paper processing, pick **one engine** and **one mode** per batch.

### Engines

| User says | Engine | Read |
|-----------|--------|------|
| "use current coding agent" / "use you" / "no external AI" | `coding-agent` | `engines/coding_agent.md` (full / metadata-only / enrich; full+enrich gated for quota) |
| "with gemini cli" / "use gemini cli" / "via gemini cli" | `gemini-cli` | `engines/gemini_cli.md` |
| "use gemini" / "with gemini" (no "cli") | ASK first | `AskUserQuestion`: "Gemini via OpenRouter (script) or Gemini CLI (direct)?" |
| anything else (default) | `openrouter` | `engines/openrouter.md` |

### Modes

| User says | Mode | Read |
|-----------|------|------|
| "enrich `<folder>`" / "summarize the existing folder `<folder>`" / "add a summary to `<folder>`" / "fill in `<folder>`" / "complete metadata for `<folder>`" | `enrich` | `modes/enrich.md` (uses `enrich.py`, NOT `paper_summarizer.py`) |
| "with summary" / "full summary" / "AI summary" | `full` | `modes/full.md` |
| "metadata only" / "no summary" / "without summary" | `metadata-only` | `modes/metadata_only.md` |
| no mode mention, brand-new PDF | ASK | `AskUserQuestion`: "Full summary or metadata only?" |
| no mode mention, user pointed at an existing folder | `enrich` | default to `enrich`; confirm summary unless user said "no summary" |

### Tags

| Trigger | Read |
|---------|------|
| user asks "process tag additions" / "pick up new tags" / mentions `tag_initialization.md` | `tags/initialize_tag_system.md` → run **§2 only if the additions file is missing**, then **§3** |
| just finished a batch (any mode) | `tags/post_summary_update.md` → run the **post-summary update flow** |
| user asks for "periodic tag check" / "audit tags" / "tag system check" / "clean up tags" | `tags/periodic_check.md` → run the **periodic-check flow** |

## Critical rules (apply always)

- Treat `.venv` as disposable local state. In iCloud-synced vaults, never preserve or share `.venv` across machines. If a `uv` command fails because the environment is stale or broken, run `uv sync` from `paperhub_utils/`; if it still fails, run `rm -rf .venv` and then `uv sync`.
- **NEVER read the PDF directly** — except `engines/coding_agent.md`. In `metadata-only` mode it extracts only the first `METADATA_ONLY_PAGE_LIMIT` pages; in `full` and `enrich` modes it reads the entire PDF natively in-session and is gated by the quota `AskUserQuestion` documented in that engine file.
- For `openrouter` and `gemini-cli`, ALWAYS delegate PDF processing to the script or `gemini` CLI. Only validate and fix the output.
- **Handle partial failures via `AskUserQuestion`** — never decide unilaterally, never auto-switch models.
- **ONLY use models from `config.py`'s `MODEL_LIST`** for `openrouter`. For `gemini-cli`, use Gemini model names.
- Metadata files MUST always include `contributions:` (empty YAML field) and `## Abstract` (verbatim from PDF when present).

## Post-AI flow

After the selected engine finishes and the paper files are written, read `shared/post_ai.md`. In brief:

1. Validate the output folder, moved PDF, metadata file, and mode-specific summary requirements.
2. Auto-fix small output issues: AI markup artifacts, tag spaces, missing required YAML fields, and missing `## Abstract`.
3. Run the batch tag handoff in `tags/post_summary_update.md` so new tags are added or merged against the registry.
4. Commit the organized files unless the user asked not to commit, `USE_GIT = False` (loaded from `paperhub_utils/misc/config.json`), or the output is outside the paper-library Git repo.
5. Report the result with token usage when available, tag updates, auto-fixes, and any failed papers.

For partial batch failures, ask the user whether to abandon, retry, or choose another allowed model. Never switch models automatically.

## Quick start

```
"Summarize this paper"                              → openrouter × ask-mode
"Summarize these papers with gemini cli"            → gemini-cli × ask-mode
"Summarize this paper. Focus on identification."    → openrouter × ask-mode + --instruction
"Enrich ACF2015"                                    → openrouter × enrich
"Add a summary to melitz2003trade with gemini cli"  → gemini-cli × enrich
```

All engines accept additional user instructions and pass them through.

## Configuration paths

| Thing | Path |
|---|---|
| Project root | current paper-library root (`PAPERHUB_ROOT` overrides auto-detection) |
| Output dir | `organized/` |
| Git repo | project root |
| Scripts | `paperhub_utils/` (`paper_summarizer.py`, `enrich.py`, `config.py`) |
| User config | `paperhub_utils/misc/config.json` (`config.py` loads and exports it) |
| Onboarding questionnaire | `onboarding_questionnaire.md` at project root (deleted after successful onboarding) |
| Prompts | `paperhub_utils/prompt/{shared,aspect}/*.txt` + `prompt/builder.py` (`prompt_template.txt` still read for `full`/`metadata-only`) |
| Tag registry | `tags/_internal/`; initial taxonomy comes from `onboarding_questionnaire.md` when present, otherwise `paperhub_utils/seeds/default_tags.yaml` |

## What this skill does NOT do

- Does NOT read PDFs directly (except first-N-pages in `coding-agent`).
- Does NOT ask the user for metadata — the AI generates it.
- Does NOT support custom output formats.
- Does NOT edit existing papers EXCEPT in `enrich` mode, which only patches blank meta keys and (re)writes `ai_summary.md` — never touches `contributions`/`status`/`interest`, never overwrites a non-blank field.
