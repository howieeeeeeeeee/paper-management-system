# Mode: Enrich Existing Folder

Use this mode when the user wants to add an `ai_summary.md` to a paper that is **already in `organized/`** (typically because the paper was first added in `metadata-only` mode, or the user wants to re-do / polish an existing summary). The PRIMARY job is generating the summary; patching any blank metadata fields is a secondary side effect of the same AI call.

This mode works with **OpenRouter** (default), **Agy CLI**, **Codex CLI**, and **Coding Agent** (`engines/coding_agent.md` — **high quota**, gated by `AskUserQuestion` and a 3-paper soft batch cap; reads the whole PDF in-session, hands the response back to `uv run python -m scripts.enrich --engine coding-agent --from-response` so the merge logic and metadata-patch rules below apply unchanged). Pick the engine the same way you would for a new paper.

## Trigger phrases

- "enrich `<folder>`" / "add a summary to `<folder>`" / "fill in `<folder>`"
- "generate ai_summary for `<folder>`" / "summarize the existing folder `<folder>`"
- "complete metadata for `<folder>`" (still routes here — meta-fill is the secondary job)
- "polish / redo / refine the summary for `<folder>`" (route here with past-summary reuse, see below)

If the user mentions multiple folders, batch them in a single call (OpenRouter) or process sequentially (Agy CLI or Codex CLI).

## What it does, per folder

1. Locate `{folder}/{folder}.md` and `{folder}/*.pdf`. Error if either is missing.
2. Detect blank required keys (`title`, `authors`, `year`, `journal`, `tags`) and the optional `link`. Detect whether `## Abstract` is the placeholder.
3. **If `ai_summary.md` already exists**, decide what to do via the `AskUserQuestion` flow below (do NOT rely on the script's stderr O/E/S prompt — drive it from the skill so the user gets a proper picker).
4. Build the enrich prompt (PRIMARY = summary, SECONDARY = meta patch). The prompt embeds the current metadata file verbatim, lists exactly which keys may be filled, and — if applicable — embeds the past summary as a polish reference. The script derives `paper_label` from the folder name; the AI response does not need to echo it.
5. Call the AI engine.
6. Surgically merge the returned `# metadata_patch` into the existing frontmatter — only blank fields, never `contributions` / `status` / `interest`.
7. Write `ai_summary.md` (with model + token frontmatter, plus `enriched: true`).
8. Run the standard post-summary tag flow (see `tags/post_summary_update.md`).
9. Commit: `feat(papers): enrich {folder}` (or `enrich {N} folders`).

## Existing-summary handling (AskUserQuestion flow)

For each folder where `{folder}/ai_summary.md` already exists, ask via `AskUserQuestion` BEFORE running `scripts.enrich`. If the user has already specified intent in their original message (e.g., "redo summary for ACF2015 using the previous one as a reference, emphasize identification"), skip the picker and use what they said.

**Q1 — Existing-summary action** (header: `Existing summary`):

> `ai_summary.md` already exists for `<folder>`. How should I proceed?

Options:

- **Polish past summary (Recommended)** — overwrite, embed the existing summary in the prompt as a reference draft, ask follow-up about emphasis
- **Overwrite from scratch** — overwrite without referencing the past summary
- **Meta-fill only** — keep the existing summary, just patch missing meta
- **Skip** — leave the folder untouched

If the user picks **Polish past summary**, ask **Q2 — Emphasis** (header: `Emphasis`):

> Any specific instruction for this polish? (e.g., parts to emphasize, expand, tighten)

Options:

- **No additional instruction** — just polish overall
- **Yes — I'll specify** (user types it via the Other field)

Batching multiple folders:

- If several folders need the question, ask them in **one** `AskUserQuestion` call (one question per folder, up to 4 questions per call), then chain a single Q2 if any of them picked "Polish past summary".
- If more than 4 folders need decisions, ask in waves of up to 4. Do not auto-decide on behalf of the user.

After collecting answers, partition the folders into groups and call `scripts.enrich` accordingly:

| User picked            | scripts.enrich flags                                               |
| ---------------------- | ------------------------------------------------------------- |
| Polish past summary    | `--force --use-past-summary` (+ `--instruction "..."` if any) |
| Overwrite from scratch | `--force`                                                     |
| Meta-fill only         | `--force --no-summary`                                        |
| Skip                   | omit the folder from `--folder` entirely                      |

`--force` is always passed because the skill has already gathered intent — the script's interactive O/E/S prompt is bypassed. Folders with different actions can be combined into separate `scripts.enrich` invocations or one invocation per group.

If a folder does NOT have an existing `ai_summary.md`, no question is needed — just run normally (no `--use-past-summary`, no `--force` needed).

## OpenRouter (default)

Single command, processes all folders sequentially in-process:

```bash
cd paperhub_utils
uv run python -m scripts.enrich \
  --folder ACF2015 [--folder OTHER ...] \
  [--instruction "Focus on identification."] \
  [--use-past-summary]   # embed each folder's existing ai_summary.md as a polish reference
  [--no-summary]         # patch missing meta only
  [--force]              # skip the interactive O/E/S prompt; overwrite
  [--model MODEL_ID]
```

`--use-past-summary` is a no-op for folders that don't have an existing summary, and is auto-disabled when `--no-summary` is set (you can't polish a summary you're not generating).

For an explicit past-summary path (rare — only when you want to point at a different file than `{folder}/ai_summary.md`), use `--past-summary-file PATH`. This is only valid with a single `--folder`.

The interactive stderr prompt fires only when `--force` is omitted; the skill should always pass `--force` after running the AskUserQuestion flow above.

## Agy CLI

Same handshake pattern as `engines/agy_cli.md` — process **one folder at a time**. The model is resolved from `config.AGY_CLI_MODEL` (configured via `paperhub_utils/config/config.json` key `agy_cli_model`) unless the user requests an allowed `--agy-model`. The prepare step persists the selected model to `~/.gemini/antigravity-cli/settings.json`.

This is the third Agy-supported mode: unlike `full` and `metadata-only`, it uses `scripts.enrich` instead of `scripts.paper_summarizer`, but it uses the same Agy `--add-dir`, absolute `@PDF`, sentinel, stderr/log, and model-label pattern.

```bash
# 1. Prepare prompt + PDF path and persist the Agy model.
cd paperhub_utils
uv run python -m scripts.enrich --engine agy-cli --prepare-cli-input --folder ACF2015 \
  [--instruction "..."] \
  [--use-past-summary] \
  [--no-summary] \
  > /tmp/paperhub_enrich_input.json

# 2. Call Agy from the repo root with an absolute @PDF path.
cd ..
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_enrich_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_input.json'))['pdf_for_ai_agy_path'])")
PAPERHUB_ROOT=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_input.json'))['paperhub_root'])")
MODEL_LABEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_input.json'))['agy_model_label'])")
AGY_LOG="/tmp/paperhub_enrich_agy.log"
AGY_STDERR="/tmp/paperhub_enrich_agy_stderr.txt"
AGY_OUTPUT="/tmp/paperhub_enrich_agy_output.txt"

agy --log-file "${AGY_LOG}" \
  --print-timeout 10m \
  --add-dir "${PAPERHUB_ROOT}" \
  --print "@${PDF_PATH}

Use only the attached PDF. Do not use web search. Do not infer from the filename.

Return the complete PaperHub response between these exact sentinel lines:
PAPERHUB_RESPONSE_BEGIN
[response]
PAPERHUB_RESPONSE_END

${PROMPT}" \
  2>"${AGY_STDERR}" > "${AGY_OUTPUT}"

# 3. Apply raw Agy output. The script extracts the sentinel block.
cd paperhub_utils
uv run python -m scripts.enrich --engine agy-cli --from-response --folder ACF2015 \
  --response-file "${AGY_OUTPUT}" \
  --model-label "${MODEL_LABEL}" \
  --agy-stderr-file "${AGY_STDERR}" \
  --agy-log-file "${AGY_LOG}"

# 4. Cleanup
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_input.json'))['cleanup_dir'])")
uv run python -m scripts.enrich --cleanup-cli-input "${CLEANUP_DIR}"
```

The past-summary text (when `--use-past-summary` is passed) is baked into the prepared prompt during step 1, so step 3 (`--from-response`) does not need any extra flag.

The prepared JSON includes `"past_summary_used": true|false` so the skill can confirm the reference was embedded.

## Codex CLI

Same handshake pattern as `engines/codex_cli.md` — process **one folder at a time**. The model/reasoning pair is resolved from `config.CODEX_CLI_MODEL` and `config.CODEX_CLI_REASONING_EFFORT` (configured via `paperhub_utils/config/config.json` keys `codex_cli_model` and `codex_cli_reasoning_effort`) unless the user requests an allowed `--codex-model` and/or `--codex-reasoning-effort`.

This is the third Codex-supported mode: unlike `full` and `metadata-only`, it uses `scripts.enrich` instead of `scripts.paper_summarizer`, but it uses the same `codex exec`, sentinel, stderr, and model-label pattern.

```bash
# 1. Prepare prompt + PDF path and resolve the Codex model/reasoning pair.
cd paperhub_utils
PAPERHUB_ROOT=$(cd .. && pwd)
uv run python -m scripts.enrich --engine codex-cli --prepare-cli-input --folder ACF2015 \
  [--instruction "..."] \
  [--use-past-summary] \
  [--no-summary] \
  > /tmp/paperhub_enrich_codex_input.json

# 2. Call Codex with local yolo/full access from the PaperHub root.
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['pdf_for_ai_codex_path'])")
CODEX_MODEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['codex_cli_model'])")
CODEX_REASONING_EFFORT=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['codex_cli_reasoning_effort'])")
MODEL_LABEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['codex_model_label'])")
CODEX_STDERR="/tmp/paperhub_enrich_codex_stderr.txt"
CODEX_OUTPUT="/tmp/paperhub_enrich_codex_output.txt"

codex exec \
  --cd "$PAPERHUB_ROOT" \
  --dangerously-bypass-approvals-and-sandbox \
  --ephemeral \
  --model "$CODEX_MODEL" \
  -c "model_reasoning_effort=\"${CODEX_REASONING_EFFORT}\"" \
  -c 'web_search="disabled"' \
  "You are running the PaperHub Codex CLI workflow.

Read and analyze the PDF at this absolute path:
${PDF_PATH}

Use only that PDF. Do not use web search. Do not infer from the filename. Do not edit files.

Return the complete PaperHub response between these exact sentinel lines:
PAPERHUB_RESPONSE_BEGIN
[response]
PAPERHUB_RESPONSE_END

${PROMPT}" \
  2>"${CODEX_STDERR}" > "${CODEX_OUTPUT}"

# 3. Apply raw Codex output. The script extracts the sentinel block.
uv run python -m scripts.enrich --engine codex-cli --from-response --folder ACF2015 \
  --response-file "${CODEX_OUTPUT}" \
  --model-label "${MODEL_LABEL}" \
  --codex-stderr-file "${CODEX_STDERR}"

# 4. Cleanup
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_codex_input.json'))['cleanup_dir'])")
uv run python -m scripts.enrich --cleanup-cli-input "${CLEANUP_DIR}"
```

The past-summary text (when `--use-past-summary` is passed) is baked into the prepared prompt during step 1, so step 3 (`--from-response`) does not need any extra flag.

## Output JSON

```json
{
  "total": 2,
  "succeeded": 2,
  "skipped": 0,
  "failed": 0,
  "results": [
    {
      "paper_label": "ACF2015",
      "folder": "organized/ACF2015",
      "filled_keys": ["link", "tags", "## Abstract"],
      "summary": "overwritten",
      "summary_path": "organized/ACF2015/ai_summary.md",
      "past_summary_used": true,
      "model": "moonshotai/kimi-k2.6",
      "usage": {"prompt_tokens": 50000, "completion_tokens": 7000, "total_tokens": 57000}
    }
  ]
}
```

`summary` is one of: `generated`, `overwritten`, `skipped`, `missing-from-response`. `past_summary_used` is only present when the past summary was embedded.

If the OpenRouter/Agy call succeeds but parsing still fails, `scripts.enrich` saves
the raw model text under `paperhub_utils/output/raw_outputs/` and returns
`raw_content_file` in the failed result so the response can be repaired with
`--from-response` instead of spending another API call.

## Reporting to the user

After all folders finish:

```text
Enriched 2 paper(s):
  ACF2015 — summary overwritten (polished from past), filled link/tags/abstract
  melitz2003trade — summary generated (no past), no meta changes
Token usage: ... (sum across folders)
Tag updates: ... (from post-summary tag flow)
Git: Committed "feat(papers): enrich 2 folders"
```

Mention "polished from past" for any folder where `past_summary_used` is true so the user knows the reference was applied.

## What this mode does NOT do

- Does NOT touch `contributions`, `status`, `interest` (user-curated).
- Does NOT overwrite any non-blank existing field.
- Does NOT rename the folder or change `paper_label`.
- Does NOT run on folders without a PDF or without `{folder}.md` — those are skipped with an error.
- Does NOT silently overwrite an existing `ai_summary.md` — the skill always asks first via `AskUserQuestion` (unless the user already stated their intent).
