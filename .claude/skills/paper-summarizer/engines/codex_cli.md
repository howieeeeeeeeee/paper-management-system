# Workflow: Codex CLI

This document covers the **OpenAI Codex CLI** paper summarization workflow. Read this file when the user requests "codex cli", "use codex cli", or a direct OpenAI CLI workflow.

## Prerequisites

- `codex` CLI installed and authenticated.
- The default PaperHub Codex model/reasoning pair is configured in `paperhub_utils/config/config.json` as `codex_cli_model` and `codex_cli_reasoning_effort`, exported as `config.CODEX_CLI_MODEL` and `config.CODEX_CLI_REASONING_EFFORT`.
- Default pair: `gpt-5.5` + `xhigh` reasoning.
- The allowed pairs live in `config.CODEX_CLI_MODEL_REASONING_PAIRS`. Current allowed pairs are `gpt-5.5+low`, `gpt-5.5+medium`, `gpt-5.5+high`, and `gpt-5.5+xhigh`.
- If the user requests a different allowed Codex model or thinking level, pass `--codex-model "MODEL_ID"` and/or `--codex-reasoning-effort "EFFORT"` to `--prepare-cli-input`.
- Codex exposes per-run model selection as `codex exec --model MODEL` / `-m MODEL`. Thinking level is passed as a per-run config override: `-c "model_reasoning_effort=\"${CODEX_REASONING_EFFORT}\""`. PaperHub does not write Codex global settings.
- PaperHub's Codex workflow uses local yolo/full-access mode by default (`codex_cli_yolo: true`) for smooth local-folder runs. `--cd "$PAPERHUB_ROOT"` sets the working root, but yolo removes OS-level sandboxing; keep this for trusted PaperHub folders only.
- The standard workflow captures the final Codex message, not JSONL events. Record model as `<model> (<effort> reasoning) (Codex CLI)`, `pdf_engine: codex-cli`, and token fields as `N/A` unless you explicitly run `codex exec --json` and pass token counts to `--from-response`.

## Overview

This workflow reuses the same prompt and file-organization logic as the OpenRouter and Agy workflows:

1. Call `uv run python -m scripts.paper_summarizer --prepare-cli-input --external-cli-engine codex-cli` to prepare the prompt/PDF and resolve the selected Codex model/reasoning pair.
2. Call `codex exec` with `--cd "$PAPERHUB_ROOT"`, `--dangerously-bypass-approvals-and-sandbox`, `--model "$CODEX_MODEL"`, and `-c "model_reasoning_effort=\"${CODEX_REASONING_EFFORT}\""`.
3. Save Codex final output and stderr files.
4. Call `uv run python -m scripts.paper_summarizer --from-response --external-cli-engine codex-cli`; the script validates Codex artifacts, extracts the sentinel-delimited response block, and organizes the paper.

In `metadata-only` mode, `--prepare-cli-input` creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF under `.paperhub_tmp/`; Codex receives that temporary PDF path, while `--from-response` still moves the original PDF into `organized/`.

**Critical Codex path rule:** Always run the PaperHub preparation/apply commands from `paperhub_utils/`. Set `PAPERHUB_ROOT=$(cd .. && pwd)` first, then run `codex exec --cd "$PAPERHUB_ROOT"` with the absolute PDF path from `pdf_for_ai_codex_path`.

## Mode Mapping

| PaperHub mode | Prepare command | Apply command | Output |
|---|---|---|---|
| `full` | `uv run python -m scripts.paper_summarizer --prepare-cli-input --external-cli-engine codex-cli --summary-mode full` | `uv run python -m scripts.paper_summarizer --from-response --external-cli-engine codex-cli --summary-mode full` | metadata note + `ai_summary.md` |
| `metadata-only` | `uv run python -m scripts.paper_summarizer --prepare-cli-input --external-cli-engine codex-cli --summary-mode metadata-only` | `uv run python -m scripts.paper_summarizer --from-response --external-cli-engine codex-cli --summary-mode metadata-only` | metadata note only; no `ai_summary.md` |
| `enrich` | `uv run python -m scripts.enrich --engine codex-cli --prepare-cli-input --folder FOLDER` | `uv run python -m scripts.enrich --engine codex-cli --from-response --folder FOLDER` | existing folder patched and/or `ai_summary.md` written |

Use the same Codex call shape for all three modes: read `prompt_path`, `pdf_for_ai_codex_path`, `paperhub_root`, `codex_cli_model`, `codex_cli_reasoning_effort`, `codex_cli_yolo`, and `codex_model_label` from the prepared JSON, then pass raw output to the matching `--from-response` command.

## Full Or Metadata-Only Paper

```bash
# From paperhub_utils/
cd paperhub_utils
PAPERHUB_ROOT=$(cd .. && pwd)

# 1. Prepare prompt/PDF and resolve the configured Codex model/reasoning pair.
uv run python -m scripts.paper_summarizer --prepare-cli-input \
  --external-cli-engine codex-cli \
  --pdf-path-arg "$PAPERHUB_ROOT/to_be_organized/paper.pdf" \
  --summary-mode full \
  > /tmp/paperhub_codex_input.json
```

Use `--summary-mode metadata-only` for metadata-only mode.

Add `--codex-model "gpt-5.5"` or `--codex-reasoning-effort "xhigh"` only when the user explicitly requests a different allowed model/thinking pair. If unspecified, the default is `gpt-5.5` + `xhigh`.

```bash
# 2. Call Codex (still in paperhub_utils/).
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_codex_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['pdf_for_ai_codex_path'])")
CODEX_MODEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['codex_cli_model'])")
CODEX_REASONING_EFFORT=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['codex_cli_reasoning_effort'])")
CODEX_OUTPUT="/tmp/paperhub_codex_output.txt"
CODEX_STDERR="/tmp/paperhub_codex_stderr.txt"

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
```

```bash
# 3. Organize from raw Codex output (still in paperhub_utils/).
ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['original_pdf_path'])")
SUMMARY_MODE=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['summary_mode'])")
MODEL_LABEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['codex_model_label'])")

uv run python -m scripts.paper_summarizer --from-response \
  --external-cli-engine codex-cli \
  --response-file "${CODEX_OUTPUT}" \
  --pdf-path-arg "${ORIGINAL_PDF}" \
  --summary-mode "${SUMMARY_MODE}" \
  --model-label "${MODEL_LABEL}" \
  --codex-stderr-file "${CODEX_STDERR}"
```

```bash
# 4. Clean up prepared prompt/temp PDF.
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_codex_input.json'))['cleanup_dir'])")
uv run python -m scripts.paper_summarizer --cleanup-cli-input "${CLEANUP_DIR}"
```

## Validation Guards

Hard-fatal — do **not** organize output:

- Codex stdout is missing `PAPERHUB_RESPONSE_BEGIN` or `PAPERHUB_RESPONSE_END`, or the response block is empty.
- Codex stderr indicates authentication, rate-limit, permission, or file-read failures.

The `--from-response --external-cli-engine codex-cli` command enforces this via `validate_codex_cli_run` in `cli_workflow/codex.py`.

## Reasoning And Yolo Settings

- Set the default model in `paperhub_utils/config/config.json` with `codex_cli_model`.
- Set the default thinking level with `codex_cli_reasoning_effort`. Current supported values for `gpt-5.5` are `low`, `medium`, `high`, and `xhigh`.
- Set `codex_cli_yolo` to `true` for the local full-access flow. The command starts Codex in the PaperHub root with `--cd "$PAPERHUB_ROOT"`, disables web search with `-c 'web_search="disabled"'`, and instructs Codex not to edit files. Yolo/full-access itself is not an OS-level folder restriction.
- If the user wants sandboxed Codex runs later, set `codex_cli_yolo` to `false` and replace `--dangerously-bypass-approvals-and-sandbox` with `--sandbox read-only -c 'approval_policy="never"'` in the command shape.

## Batches

Process Codex CLI papers sequentially by default. If the user explicitly wants parallelism, only batch papers using the same resolved Codex model/reasoning pair and keep per-paper output/stderr paths distinct.

## Error Handling

If Codex fails, ask the user whether to retry Codex, switch to OpenRouter, choose a different allowed Codex model/reasoning pair, or abandon the paper. Never silently switch engines or models.

For parse failures, `uv run python -m scripts.paper_summarizer --from-response` saves raw content under `paperhub_utils/output/raw_outputs/`. Do not manually rewrite the response with agent tokens. Ask before doing an AI format-repair retry.

## Completion Reporting

In `full` mode, `ai_summary.md` frontmatter should show:

```yaml
---
model: gpt-5.5 (xhigh reasoning) (Codex CLI)
pdf_engine: codex-cli
tokens_prompt: N/A
tokens_completion: N/A
total_tokens: N/A
cost: N/A
generated: 2026-06-22 14:30:00
---
```

In reports, say token usage is unavailable from the standard Codex CLI flow and show `Cost: N/A`.
