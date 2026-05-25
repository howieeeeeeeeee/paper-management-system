# Workflow: Agy CLI

This document covers the **Agy CLI / Google Antigravity CLI** paper summarization workflow. Read this file when the user requests "agy cli", "antigravity cli", or a direct Google CLI workflow. This is the active replacement for the old Gemini CLI workflow.

## Prerequisites

- `agy` CLI installed and authenticated with the user's Google account.
- The default PaperHub Agy model is configured in `paperhub_utils/misc/config.json` as `agy_cli_model`, exported as `config.AGY_CLI_MODEL`.
- Default model: `Gemini 3.1 Pro (High)`.
- If the user requests a different Agy model, pass `--agy-model "MODEL LABEL"` to `--prepare-cli-input`. The script validates it against `config.AGY_CLI_MODEL_LIST`, writes it to `~/.gemini/antigravity-cli/settings.json`, and leaves that setting in place.
- Agy does not currently expose a per-run `--model` flag or Gemini-style `-o json` token stats. Record model as `<model> (Agy CLI)`, `pdf_engine: agy-native`, and token fields as `N/A`.

## Overview

This workflow reuses the same prompt and file-organization logic as the OpenRouter workflow:

1. Call `paper_summarizer.py --prepare-cli-input --external-cli-engine agy-cli` to prepare the prompt/PDF and persist the selected Agy model.
2. Call `agy --print` from the paper-library root, with `--add-dir "$PAPERHUB_ROOT"` and an absolute `@PDF` attachment.
3. Save raw Agy stdout/stderr/log files.
4. Call `paper_summarizer.py --from-response --external-cli-engine agy-cli`; the script validates Agy artifacts, extracts the sentinel-delimited response block, and organizes the paper.

In `metadata-only` mode, `--prepare-cli-input` creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF under `.paperhub_tmp/`; Agy receives that temporary PDF, while `--from-response` still moves the original PDF into `organized/`.

**Critical Agy path rule:** use the absolute PDF path from `pdf_for_ai_agy_path` and always pass `--add-dir "$PAPERHUB_ROOT"`. Agy may otherwise resolve `@organized/...` relative to a parent project and fail to read the PDF.

## Mode Mapping

| PaperHub mode | Prepare command | Apply command | Output |
|---|---|---|---|
| `full` | `paper_summarizer.py --prepare-cli-input --external-cli-engine agy-cli --summary-mode full` | `paper_summarizer.py --from-response --external-cli-engine agy-cli --summary-mode full` | metadata note + `ai_summary.md` |
| `metadata-only` | `paper_summarizer.py --prepare-cli-input --external-cli-engine agy-cli --summary-mode metadata-only` | `paper_summarizer.py --from-response --external-cli-engine agy-cli --summary-mode metadata-only` | metadata note only; no `ai_summary.md` |
| `enrich` | `enrich.py --engine agy-cli --prepare-cli-input --folder FOLDER` | `enrich.py --engine agy-cli --from-response --folder FOLDER` | existing folder patched and/or `ai_summary.md` written |

Use the same Agy call shape for all three modes: read `prompt_path`, `pdf_for_ai_agy_path`, `paperhub_root`, and `agy_model_label` from the prepared JSON, then pass raw stdout to the matching `--from-response` command.

## Full Or Metadata-Only Paper

```bash
# 1. Prepare prompt/PDF and persist the configured Agy model.
cd paperhub_utils
uv run python paper_summarizer.py --prepare-cli-input \
  --external-cli-engine agy-cli \
  --pdf-path-arg "../to_be_organized/paper.pdf" \
  --summary-mode full \
  > /tmp/paperhub_agy_input.json
```

Use `--summary-mode metadata-only` for metadata-only mode. Do not change the Agy call shape; the prepared JSON will point Agy at the first-pages temp PDF.

Add `--agy-model "Gemini 3.5 Flash (Medium)"` only when the user explicitly requests a different allowed Agy model.

```bash
# 2. Call Agy from the paper-library root.
cd ..
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_agy_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['pdf_for_ai_agy_path'])")
PAPERHUB_ROOT=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['paperhub_root'])")
AGY_LOG="/tmp/paperhub_agy.log"
AGY_STDERR="/tmp/paperhub_agy_stderr.txt"
AGY_OUTPUT="/tmp/paperhub_agy_output.txt"

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
```

```bash
# 3. Organize from raw Agy output. The script extracts the sentinel block.
cd paperhub_utils
ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['original_pdf_path'])")
SUMMARY_MODE=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['summary_mode'])")
MODEL_LABEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['agy_model_label'])")

uv run python paper_summarizer.py --from-response \
  --external-cli-engine agy-cli \
  --response-file "${AGY_OUTPUT}" \
  --pdf-path-arg "${ORIGINAL_PDF}" \
  --summary-mode "${SUMMARY_MODE}" \
  --model-label "${MODEL_LABEL}" \
  --agy-stderr-file "${AGY_STDERR}" \
  --agy-log-file "${AGY_LOG}"
```

```bash
# 4. Clean up prepared prompt/temp PDF.
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['cleanup_dir'])")
uv run python paper_summarizer.py --cleanup-cli-input "${CLEANUP_DIR}"
```

## Validation Guards

Treat these as fatal and do **not** organize output:

- Agy exits with `Error: timed out waiting for response`.
- Agy stdout is missing `PAPERHUB_RESPONSE_BEGIN` or `PAPERHUB_RESPONSE_END`.
- Agy stderr/log contains file-read or workspace failures.
- Agy stderr/log contains visible tool-call failures or web-search markers.

The `--from-response --external-cli-engine agy-cli` command enforces these via `cli_workflow/agy.py`.

## Batches

Process Agy papers sequentially by default. Parallel calls share the same global Agy settings file and are harder to debug. If the user explicitly wants parallelism, only batch papers using the same resolved Agy model and keep per-paper output/stderr/log paths distinct.

## Error Handling

If Agy fails, ask the user whether to retry Agy, switch to OpenRouter, choose a different allowed Agy model, or abandon the paper. Never silently switch engines or models.

For parse failures, `paper_summarizer.py --from-response` saves raw content under `paperhub_utils/raw_outputs/`. Do not manually rewrite the response with agent tokens. Ask before doing an AI format-repair retry.

## Completion Reporting

In `full` mode, `ai_summary.md` frontmatter should show:

```yaml
---
model: Gemini 3.1 Pro (High) (Agy CLI)
pdf_engine: agy-native
tokens_prompt: N/A
tokens_completion: N/A
total_tokens: N/A
cost: N/A
generated: 2026-05-24 14:30:00
---
```

In reports, say token usage is unavailable from Agy CLI and show `Cost: N/A`.
