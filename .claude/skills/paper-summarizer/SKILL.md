---
name: paper-summarizer
description: Automated research paper organization using AI. Triggers when users ask to onboard, set up, configure, or first-run this paper library; when users upload PDFs and ask to summarize, organize, or add papers to their library; or when they ask to enrich an existing folder with an AI summary. Supports OpenRouter, Agy CLI, and current-coding-agent engines across full / metadata-only / enrich modes.
---

# Research Paper Summarizer

Routes the user's request to the right `engine × mode`, then delegates to a per-doc playbook. **Read only the doc(s) you need** — don't load unrelated ones.

## File map

```
SKILL.md                  ← you are here (router only)
onboard.md                ← questionnaire-first setup inside an Obsidian vault
engines/
  openrouter.md           ← default; uses paper_summarizer.py via OpenRouter API
  agy_cli.md              ← active direct-Google CLI workflow via `agy`
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
| "with agy cli" / "use antigravity cli" / "direct Google CLI" | `agy-cli` | `engines/agy_cli.md` |
| "with gemini cli" / "use gemini cli" / "via gemini cli" | `agy-cli` | `engines/agy_cli.md` — Gemini CLI has been replaced by Agy CLI (Google Antigravity) |
| "use gemini" / "with gemini" (no "cli") | ASK first | `AskUserQuestion`: "Gemini via OpenRouter (script) or Agy CLI (direct Google CLI)?" |
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

- **Paths with spaces:** Pass literal paths (spaces as-is) to `Read`, `Edit`, and `Write` tools — do NOT backslash-escape spaces. Backslash escaping is only for Bash tool commands. If the project root contains spaces, escaping will cause "file not found" errors even when the file exists.
- **uv run location:** Always `cd paperhub_utils` before running `uv run` commands, since `pyproject.toml` and `.venv` are stored there. Example: `cd paperhub_utils && uv run python paper_summarizer.py ... && cd ..`
- **Batch processing paths:** Always cd into `paperhub_utils` first. Use `PAPERHUB_ROOT=$(cd .. && pwd)` to get the PaperHub root (works on any machine). For Agy: use `agy --add-dir "$PAPERHUB_ROOT"` and PDF paths from the prepared JSON.
- Treat `.venv` as disposable local state. In iCloud-synced vaults, never preserve or share `.venv` across machines. If a `uv` command fails because the environment is stale or broken, run `uv sync` from `paperhub_utils/`; if it still fails, run `rm -rf .venv` and then `uv sync`.
- **NEVER read the PDF directly** — except `engines/coding_agent.md`. In `metadata-only` mode it extracts only the first `METADATA_ONLY_PAGE_LIMIT` pages; in `full` and `enrich` modes it reads the entire PDF natively in-session and is gated by the quota `AskUserQuestion` documented in that engine file.
- For `openrouter` and `agy-cli`, ALWAYS delegate PDF processing to the script or external CLI. Only validate and fix the output.
- **Handle partial failures via `AskUserQuestion`** — never decide unilaterally, never auto-switch models.
- **ONLY use models from `config.py`'s `MODEL_LIST`** for `openrouter`. For `agy-cli`, use `AGY_CLI_MODEL_LIST`; the selected model is persisted to Agy settings by `--prepare-cli-input`.
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
"Summarize these papers with agy cli"               → agy-cli × ask-mode
"Summarize these papers with gemini cli"            → agy-cli × ask-mode (Gemini CLI replaced by Agy CLI)
"Summarize this paper. Focus on identification."    → openrouter × ask-mode + --instruction
"Enrich ACF2015"                                    → openrouter × enrich
"Add a summary to melitz2003trade with agy cli"     → agy-cli × enrich
```

All engines accept additional user instructions and pass them through.

## Batch Processing (Multiple Papers)

For batch workflows with **Agy CLI in parallel**:

1. **Prepare:** `cd paperhub_utils`, call `--prepare-cli-input` for each paper, store JSONs as `prepare_1.json`, `prepare_2.json`, etc.
2. **Call Agy in parallel:** Stay in `paperhub_utils`, launch background jobs with `--add-dir ..` (points to PaperHub root). Use numbered output files (`agy_output_1.txt`, `agy_stderr_1.txt`, `agy_log_1.log`).
3. **Wait & process:** After `wait`, call `--from-response` sequentially for each paper (still in `paperhub_utils`).
4. **Cleanup:** Call `--cleanup-cli-input` for each prepared temp PDF.

### Parallel Agy CLI Example

```bash
cd paperhub_utils
PAPERHUB_ROOT=$(cd .. && pwd)

# 1. Prepare all papers
for paper in "$PAPERHUB_ROOT"/to_be_organized/*.pdf; do
  uv run python paper_summarizer.py --prepare-cli-input \
    --external-cli-engine agy-cli \
    --pdf-path-arg "$paper" \
    --summary-mode full > "/tmp/prepare_$(basename "$paper").json"
done

# 2. Run Agy in parallel with distinct output files
for i in {1..4}; do {
  PDF=$(python3 -c "import json; print(json.load(open(...))['pdf_for_ai_agy_path'])")
  agy --add-dir "$PAPERHUB_ROOT" --print "@$PDF\n...[prompt]..." > "/tmp/agy_output_$i.txt" 2> "/tmp/agy_stderr_$i.txt"
} & done
wait

# 3. Process responses sequentially
for i in {1..4}; do
  uv run python paper_summarizer.py --from-response \
    --external-cli-engine agy-cli \
    --response-file "/tmp/agy_output_$i.txt" ...
done
```

**Key safeguards:**
- Stay in `paperhub_utils/` throughout (ensures `uv run` finds `.venv` and `pyproject.toml`).
- Use `PAPERHUB_ROOT=$(cd .. && pwd)` (works on any machine, no hardcoded paths).
- Use `agy --add-dir "$PAPERHUB_ROOT"` for absolute workspace reference.
- Output/stderr/log files are numbered to prevent collisions.
- Wait for all background jobs before processing responses.

## Configuration paths

| Thing | Path |
|---|---|
| Project root | current paper-library root (`PAPERHUB_ROOT` overrides auto-detection) |
| Output dir | `organized/` |
| Git repo | project root |
| Scripts | `paperhub_utils/` (`paper_summarizer.py`, `enrich.py`, `config.py`) |
| User config | `paperhub_utils/misc/config.json` (`config.py` loads and exports it) |
| Onboarding questionnaire | `onboarding_questionnaire.md` at project root (deleted after successful onboarding) |
| Prompts | `paperhub_utils/prompt/{shared,aspect}/*.txt` + `prompt/builder.py` (all modes compose from fragments) |
| Tag registry | `tags/_internal/`; initial taxonomy comes from `onboarding_questionnaire.md` when present, otherwise `paperhub_utils/seeds/default_tags.yaml` |

## What this skill does NOT do

- Does NOT read PDFs directly (except first-N-pages in `coding-agent`).
- Does NOT ask the user for metadata — the AI generates it.
- Does NOT support custom output formats.
- Does NOT edit existing papers EXCEPT in `enrich` mode, which only patches blank meta keys and (re)writes `ai_summary.md` — never touches `contributions`/`status`/`interest`, never overwrites a non-blank field.
