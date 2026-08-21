---
name: paper-organizer
description: Organize research papers from local PDFs or public paper links. Use for PaperHub onboarding, PDF metadata/full summaries, parallel mixed-link batches, link metadata and abstracts, batches from Markdown link lists, or enriching existing folders. Supports OpenRouter, Agy CLI, Codex CLI, and current-coding-agent engines while keeping external link-engine calls offline.
---

# Research Paper Organizer

Routes the user's request to the right `engine × mode`, then delegates to a per-doc playbook. **Read only the doc(s) you need** — don't load unrelated ones.

## File map

```
SKILL.md                  ← you are here (router only)
onboard.md                ← questionnaire-first setup inside an Obsidian vault
link_input.md             ← URL/list preprocessing and offline engine handshake
engines/
  openrouter.md           ← uses `scripts.paper_organizer` via OpenRouter API
  agy_cli.md              ← active direct-Google CLI workflow via `agy`
  codex_cli.md            ← OpenAI Codex CLI workflow via `codex exec`
  coding_agent.md         ← in-process; full / metadata-only / enrich (high quota for full+enrich)
modes/
  full.md                 ← writes {paper_label}.md + ai_summary.md
  metadata_only.md        ← writes {paper_label}.md only (sends first N pages)
  enrich.md               ← writes ai_summary.md for an EXISTING folder; patches blank meta
shared/
  post_ai.md              ← validation, autofix, optional citations, tags, related-paper labels, versioning, partial-failure handling
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

**Engine selection precedence.** Before reading config, scan the user's request
for a named engine (`codex`, `agy`/`antigravity`, `openrouter`, `gemini`, or the
current agent). A named engine is binding and outranks every default below; the
availability gate may then verify or refuse it, but never replaces it with a
different engine. Only when the request names none does the default in the
Engines table apply.

### Engine availability gate (verifies a choice; never makes one)

Before recommending, selecting, or invoking an AI engine, read `AVAILABLE_ENGINES`
from `paperhub.config` (backed by `available_engines` in
`paperhub_utils/config/config.json`). Canonical IDs are `coding-agent`,
`codex-cli`, `agy-cli`, and `openrouter`.

1. Treat `coding-agent` as available unconditionally. `paperhub.config` adds it
   even when the config key is missing or malformed.
2. Suggest or offer only engines in `AVAILABLE_ENGINES`. Keep their configured
   order and always include the current coding agent as a choice. Do not suggest
   an unlisted external engine merely because its executable or API key happens
   to exist.
3. If the user explicitly requests an external engine that is not listed:
   - Tell them it is not currently enabled and show the enabled choices.
   - Ask whether they want to verify the requested engine. If not, let them
     choose only from the enabled list.
   - For `openrouter`, verify that `OPENROUTER_API_KEY` loads without printing it.
     For `agy-cli`, verify the executable and have the user confirm it launches
     signed in. For `codex-cli`, run `command -v codex && codex exec --help` and
     confirm authentication when the command cannot prove it.
   - Do not append the engine when verification fails. If an executable check
     cannot prove authentication, allow the requested first run but wait for
     that run to succeed before appending it.
   - After verification or the first real invocation succeeds, append the
     canonical ID to `available_engines` in `config.json`, preserving existing
     order and all unrelated settings. Ensure `coding-agent` remains present.
4. If an enabled external engine later fails, follow its normal failure flow;
   do not silently switch engines or remove it from the list.
5. When the user names no engine, default to `coding-agent`. Never reach for an
   external engine on your own; the user must name it. Any engine-selection
   question must contain only listed engines plus the current agent.

For paper processing, first identify the input kind. For a URL or Markdown/plain-
text link list, read `link_input.md`. For a local PDF or existing folder, pick
**one engine** and **one mode** per batch below.

### New local-PDF duplicate preflight

Before asking for a mode, selecting an engine, preparing a prompt, or sending any
**new local PDF** to an engine, check whether `organized/` already contains a PDF
with the same filename. This checkpoint applies to local PDF inputs only (for
example, files in `to_be_organized/` or another local path). Do not run it for
URL/link ingestion, which has its own canonical-link duplicate check, or for
`enrich`, which intentionally targets an existing folder.

1. Use ordinary filesystem tools, not a new utility script. List existing PDFs,
   then compare each incoming PDF's basename to those basenames with an exact,
   case-insensitive comparison. Do not use fuzzy filename matching, DOI/link
   inference, or file-content hashes.
2. Treat obviously non-identifying stems such as `main` and `paper`, including
   ordinary numbered/copy-suffixed forms, as **generic filenames**. For a generic
   exact-filename match, extract only page 1 from the incoming PDF and every
   matching organized PDF with a local tool such as
   `pdftotext -f 1 -l 1 -layout`. Identify the displayed paper titles and compare
   them case-insensitively after normalizing whitespace and punctuation.
   - If every existing title is clearly different from the incoming title, this
     is a filename collision, not a duplicate. Process the incoming PDF normally
     without asking the user.
   - If one or more titles match, retain only those same-title records as
     duplicates and continue to the checkpoint below.
   - If either title cannot be extracted confidently, keep that match as a
     potential duplicate and continue to the checkpoint below. Never infer a
     title from the filename or send first-page content to an AI engine during
     preflight.
3. For a non-generic exact-filename match, continue directly to the duplicate
   checkpoint. Collect **all** matching paths. Each match's paper folder is the
   PDF's parent; its canonical metadata note is
   `{folder}/{folder_name}.md`.
4. Read each available canonical metadata note and show the user a compact record
   containing the paper-folder path, metadata-note path, title, authors, year,
   journal, link, status, interest, and tags. For generic filenames, also show the
   incoming and existing first-page titles (or mark them unavailable). If the
   note is missing, unreadable, malformed, or lacks a field, show the paths and
   mark the unavailable values; the checkpoint still applies.
5. Use `AskUserQuestion` once per duplicate or potential-duplicate incoming PDF,
   grouping all applicable existing matches for that input. Offer:
   - `Skip and keep (Recommended)`: remove the PDF from the active batch but leave
     the incoming file in place.
   - `Skip and delete`: remove the PDF from the active batch and delete only that
     resolved incoming file. This is never the default. Prefer a recoverable
     trash operation when available; otherwise make clear that deletion is
     permanent, and report afterward whether recovery is possible.
   - `Process again`: keep the PDF in the active batch.
6. Resolve every checkpoint before starting a batch. Never send a skipped PDF to
   an engine. If all inputs are skipped and kept, report the existing records and
   stop without running post-AI, tag, or versioning flows because nothing
   changed. If any incoming PDF was deleted, skip post-AI and tag flows but run
   the normal versioning handoff because the vault changed.

If the user explicitly chooses `Process again`, continue through normal routing
but never overwrite the existing record. Script-backed engines use the existing
timestamp-suffixed collision behavior. For direct current-coding-agent writes,
when `organized/{paper_label}` already exists, create a unique
`{paper_label}_{YYYYMMDD_HHMMSS}` folder and use that suffixed name consistently
for the folder and canonical metadata filename.

### Engines

| User's request mentions | Engine | Read |
|-----------|--------|------|
| the current agent — "use you", "no external AI", "current coding agent" | `coding-agent` | `engines/coding_agent.md` (full / metadata-only / enrich; full+enrich gated for quota) |
| codex, in any phrasing — "with/use/using codex cli", "direct OpenAI CLI" | `codex-cli` | `engines/codex_cli.md` |
| agy or antigravity, in any phrasing — "direct Google CLI" | `agy-cli` | `engines/agy_cli.md` |
| openrouter, in any phrasing | `openrouter` | `engines/openrouter.md` |
| gemini, without "cli" | FILTER, then ASK if needed | Among enabled `openrouter` and `agy-cli`: route directly if one is enabled, ask which if both are enabled, or run the availability gate if neither is enabled |
| **no engine named at all** | `coding-agent` | `engines/coding_agent.md` |

Match on the engine's identity anywhere in the request, not on these exact
strings — the quoted phrases are examples. The default row applies only when no
engine is named; never reach it because a phrasing did not match verbatim.

### Modes

| User says | Mode | Read |
|-----------|------|------|
| "enrich `<folder>`" / "summarize the existing folder `<folder>`" / "add a summary to `<folder>`" / "fill in `<folder>`" / "complete metadata for `<folder>`" | `enrich` | `modes/enrich.md` (uses `scripts.enrich`, NOT `scripts.paper_organizer`) |
| "with summary" / "full summary" / "AI summary" | `full` | `modes/full.md` |
| "metadata only" / "no summary" / "without summary" | `metadata-only` | `modes/metadata_only.md` |
| URL/link list with no mode mention | `link-metadata` | `link_input.md`; default to YAML + abstract only |
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
- **uv run location:** Always `cd paperhub_utils` before running `uv run` commands, since `pyproject.toml` and `.venv` are stored there. Example: `cd paperhub_utils && uv run python -m scripts.paper_organizer ... && cd ..`
- **Batch processing paths:** Always cd into `paperhub_utils` first. Use `PAPERHUB_ROOT=$(cd .. && pwd)` to get the PaperHub root (works on any machine). For Agy: use `agy --add-dir "$PAPERHUB_ROOT"` and PDF paths from the prepared JSON. For Codex: use `codex exec --cd "$PAPERHUB_ROOT"` and PDF paths from the prepared JSON; PaperHub's default Codex path uses local yolo/full-access mode with web search disabled.
- Treat `.venv` as disposable local state. In iCloud-synced vaults, never preserve or share `.venv` across machines. If a `uv` command fails because the environment is stale or broken, run `uv sync` from `paperhub_utils/`; if it still fails, run `rm -rf .venv` and then `uv sync`.
- **NEVER read the PDF directly** — except `engines/coding_agent.md` and the first-page-only local title comparison for generic filenames in the duplicate preflight above. The duplicate preflight must not send page content to AI. In `metadata-only` mode the coding-agent engine extracts only the first `METADATA_ONLY_PAGE_LIMIT` pages; in `full` and `enrich` modes it reads the entire PDF natively in-session and is gated by the quota `AskUserQuestion` documented in that engine file.
- For `openrouter`, `agy-cli`, and `codex-cli`, ALWAYS delegate PDF processing to the script or external CLI. Only validate and fix the output.
- For links, ALWAYS run `scripts.paper_link_context` before invoking an engine.
  External engines receive only the resulting text. Keep Codex web search
  disabled, provide no OpenRouter web tools, and reject Agy web-tool markers.
  If public metadata is incomplete, the invoking coding agent may browse and
  append verified facts plus source URLs under `Coding-Agent Additions`.
- **Handle partial failures via `AskUserQuestion`** — never decide unilaterally, never auto-switch models.
- **Never satisfy a failing validation guard by creating, blanking, or editing the artifact it checks.** A guard that fires means the engine did not run as assumed; re-run it or fail the paper. Silencing it organizes the wrong paper under a plausible-looking name.
- **For external CLI engines, prove the run happened before applying its response.** Use fresh per-batch artifact paths (never fixed `/tmp` names that a previous session may have left behind), check each call's own exit code rather than a wrapper's, and never build the prompt inside a shell string — backticks and `$` in the prompt can kill the command before the engine starts.
- **ONLY use models from `paperhub.config`'s `MODEL_LIST`** for `openrouter`. For `agy-cli`, use `AGY_CLI_MODEL_LIST`; the selected model is persisted to Agy settings by `--prepare-cli-input`. For `codex-cli`, use `CODEX_CLI_MODEL_REASONING_PAIRS`; the selected model is passed per run with `codex exec --model`, and the thinking level is passed per run with `-c model_reasoning_effort=...`.
- Metadata files MUST always include `contributions:` (empty YAML field) and `## Abstract` (verbatim from PDF when present).

## Post-AI flow

After the selected engine finishes and the paper files are written, read `shared/post_ai.md`. In brief:

1. Validate the output folder, metadata file, optional PDF for link input, and mode-specific summary requirements.
2. Auto-fix small output issues: AI markup artifacts, tag spaces, missing required YAML fields, and missing `## Abstract`.
3. When `CITATION_RESOLVE_AFTER_ORGANIZE` is enabled, attempt citation resolution once without blocking the paper workflow; skip `enrich`.
4. Run the batch tag handoff in `tags/post_summary_update.md` so new tags are added or merged against the registry.
5. Reconcile generated wikilink targets under an exact `Related Papers` heading against local author-year candidates. The helper is read-only; the current coding agent changes only clearly confirmed targets and leaves ambiguous or unmatched references untouched.
6. Version the organized files by running the `versioning-with-git` skill (mirrors the vault into the out-of-iCloud git backup repo and commits/pushes there — the vault itself has no `.git`), unless the user asked not to commit. It self-skips when `USE_GIT = False` or no backup path is set (loaded from `paperhub_utils/config/config.json`).
7. Report the result with token usage when available, tag updates, related-paper reconciliation, auto-fixes, optional citation status, and any failed papers.

For partial batch failures, ask the user whether to abandon, retry, or choose another allowed model for the active engine. Never switch models automatically.

## Quick start

```
"Summarize this paper"                              → coding-agent × ask-mode (no engine named)
"Summarize these papers with agy cli"               → agy-cli × ask-mode
"Summarize these papers with codex cli"             → codex-cli × ask-mode
"Summarize these papers with openrouter"            → openrouter × ask-mode
"Summarize this paper. Focus on identification."    → coding-agent × ask-mode + --instruction
"Organize https://example.org/paper"                → coding-agent × link-metadata
"Organize links under heading X in papers to find"  → chosen engine × link-metadata
"Enrich ACF2015"                                    → coding-agent × enrich
"Add a summary to melitz2003trade with agy cli"     → agy-cli × enrich
"Add a summary to melitz2003trade with codex cli"   → codex-cli × enrich
```

All engines accept additional user instructions and pass them through.

## Batch Processing (Multiple Papers)

For a URL batch, read `link_input.md`. Preprocess every URL sequentially, then
split the results into pure links, metadata-only public PDFs, and full-summary
public PDFs. If public PDFs are pending a mode, ask once before engine calls.

- Process pure links with the managed repeated `--link-context` command. It runs
  OpenRouter, Agy, or Codex generation in parallel and finalizes outputs
  sequentially.
- Process each PDF mode as a separate batch. OpenRouter accepts all PDF paths in
  one command; Agy and Codex prepare each PDF, run up to the chosen worker limit
  concurrently with isolated artifacts, then apply responses sequentially.
- Default to four workers and allow `1-8`. Let all scheduled jobs finish after
  an individual failure, retain failed diagnostics, and never switch models.
- Reassemble the final user report in original input order and run the tag/post-
  AI handoff once after all groups are resolved.

## Configuration paths

| Thing | Path |
|---|---|
| Project root | current paper-library root (`PAPERHUB_ROOT` overrides auto-detection) |
| Output dir | `organized/` |
| Git backup repo | `git.backup_abs_path` in `config.json` — a git repo OUTSIDE iCloud; the vault has no `.git`. Commits go through the `versioning-with-git` skill |
| Entry scripts | `paperhub_utils/scripts/` (`scripts.paper_organizer`, `scripts.enrich`, `scripts.related_paper_candidates`, `scripts.paper_search`, `scripts.update_utils`) |
| Python package | `paperhub_utils/paperhub/` (`config.py`, `cli_workflow/`, `tag_utils/`, `prompt/builder.py`) |
| User config | `paperhub_utils/config/config.json` (`paperhub.config` loads and exports it) |
| Available engines | `available_engines` in `config.json`; canonicalized as `paperhub.config.AVAILABLE_ENGINES`; current coding agent is always included |
| Onboarding questionnaire | `onboarding_questionnaire.md` at project root (deleted after successful onboarding) |
| Prompts | `paperhub_utils/prompts/{shared,aspect}/*.txt` + `paperhub/prompt/builder.py` (all modes compose from fragments) |
| Tag registry | `tags/_internal/`; initial taxonomy comes from `onboarding_questionnaire.md` when present, otherwise `paperhub_utils/config/default_tags.yaml` |

## What this skill does NOT do

- Does NOT read PDFs directly (except first-N-pages in `coding-agent`).
- Does NOT ask the user for metadata when public sources can provide it; missing
  link fields remain explicit placeholders.
- Does NOT support custom output formats.
- Does NOT edit existing papers except in `enrich` mode and the post-AI related-paper step. Enrich only patches blank meta keys and (re)writes `ai_summary.md`; related-paper reconciliation may change only a confirmed wikilink target under `Related Papers`. Neither route touches `contributions`/`status`/`interest` or overwrites a non-blank metadata field.
