# Workflow: Agy CLI

This document covers the **Agy CLI** paper summarization workflow. Users may call this "Antigravity CLI"; treat that as the same engine and keep `agy-cli` as the internal route name. Read this file when the user requests "agy cli", "antigravity cli", "antigravity", or a direct Google CLI workflow.

## Prerequisites

- `agy` CLI installed and authenticated with the user's Google account.
- The default PaperHub Agy model is configured in `paperhub_utils/config/config.json` (`agy_cli_model`) and resolved by `paperhub/config.py` as `config.AGY_CLI_MODEL`. This doc does not name a default model — read it from config, or from the prepared JSON, which carries the resolved `agy_model_label`.
- The allowed Agy models are defined in `config.AGY_CLI_MODEL_LIST` (`paperhub/config.py`). Treat that constant as the single source of truth; do not enumerate the models here.
- If the user requests a different Agy model, pass `--agy-model "MODEL LABEL"` to `--prepare-cli-input`. The script validates it against `config.AGY_CLI_MODEL_LIST`, writes it to the Agy settings path, and leaves that setting in place. Set `AGY_CLI_SETTINGS_PATH` if the local install uses a custom settings location.
- Current Agy releases expose per-run `--model`; managed link batches use it to avoid shared-settings races. The compatibility PDF prepare flow still persists its validated model. Agy does not expose token stats, so record token fields as `N/A`.

## Overview

This workflow reuses the same prompt and file-organization logic as the OpenRouter workflow:

1. Call `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine agy-cli` to prepare the prompt/PDF and persist the selected Agy model.
2. Call `agy --print` from the paper-library root, with `--add-dir "$PAPERHUB_ROOT"` and an absolute `@PDF` attachment.
3. Save raw Agy stdout/stderr/log files.
4. Call `uv run python -m scripts.paper_organizer --from-response --external-cli-engine agy-cli`; the script validates Agy artifacts, extracts the sentinel-delimited response block, and organizes the paper.

In `metadata-only` mode, `--prepare-cli-input` creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF under `.paperhub_tmp/`; Agy receives that temporary PDF, while `--from-response` still moves the original PDF into `organized/`.

**Critical Agy path rule:** Always run from `paperhub_utils/`. Set `PAPERHUB_ROOT=$(cd .. && pwd)` first, then use `agy --add-dir "$PAPERHUB_ROOT"` with the PDF path from `pdf_for_ai_agy_path`. This ensures Agy resolves paths correctly on any machine.

## Mode Mapping

| PaperHub mode | Prepare command | Apply command | Output |
|---|---|---|---|
| `full` | `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine agy-cli --summary-mode full` | `uv run python -m scripts.paper_organizer --from-response --external-cli-engine agy-cli --summary-mode full` | metadata note + `ai_summary.md` |
| `metadata-only` | `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine agy-cli --summary-mode metadata-only` | `uv run python -m scripts.paper_organizer --from-response --external-cli-engine agy-cli --summary-mode metadata-only` | metadata note only; no `ai_summary.md` |
| `enrich` | `uv run python -m scripts.enrich --engine agy-cli --prepare-cli-input --folder FOLDER` | `uv run python -m scripts.enrich --engine agy-cli --from-response --folder FOLDER` | existing folder patched and/or `ai_summary.md` written |

Use the same Agy call shape for all three modes: read `prompt_path`, `pdf_for_ai_agy_path`, `paperhub_root`, and `agy_model_label` from the prepared JSON, then pass raw stdout to the matching `--from-response` command.

## Full Or Metadata-Only Paper

```bash
# From paperhub_utils/
cd paperhub_utils
PAPERHUB_ROOT=$(cd .. && pwd)

# 1. Prepare prompt/PDF and persist the configured Agy model.
uv run python -m scripts.paper_organizer --prepare-cli-input \
  --external-cli-engine agy-cli \
  --pdf-path-arg "$PAPERHUB_ROOT/to_be_organized/paper.pdf" \
  --summary-mode full \
  > /tmp/paperhub_agy_input.json
```

Use `--summary-mode metadata-only` for metadata-only mode. Do not change the Agy call shape.

Add `--agy-model "MODEL LABEL"` only when the user explicitly requests a different allowed Agy model (validated against `config.AGY_CLI_MODEL_LIST`).

```bash
# 2. Call Agy (still in paperhub_utils/).
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_agy_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['pdf_for_ai_agy_path'])")
AGY_LOG="/tmp/paperhub_agy.log"
AGY_STDERR="/tmp/paperhub_agy_stderr.txt"
AGY_OUTPUT="/tmp/paperhub_agy_output.txt"

agy --log-file "${AGY_LOG}" \
  --print-timeout 10m \
  --add-dir "$PAPERHUB_ROOT" \
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
# 3. Organize from raw Agy output (still in paperhub_utils/).
ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['original_pdf_path'])")
SUMMARY_MODE=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['summary_mode'])")
MODEL_LABEL=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agy_input.json'))['agy_model_label'])")

uv run python -m scripts.paper_organizer --from-response \
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
uv run python -m scripts.paper_organizer --cleanup-cli-input "${CLEANUP_DIR}"
```

## Validation Guards

Hard-fatal — do **not** organize output:

- Agy exits with `Error: timed out waiting for response`.
- Agy stdout is missing `PAPERHUB_RESPONSE_BEGIN` or `PAPERHUB_RESPONSE_END`, or the response block is empty.
- Agy stderr/log contains file-read or workspace failures.
- Agy stderr/log contains web-search markers.

Recoverable — tolerated when a valid, non-empty sentinel response was produced:

- `invalid tool call error` / `Model output error` in the log. Some Agy print-mode runs emit spurious agentic tool-call steps (e.g. `echo`-ing a status line), and Agy's arg-marshalling can make them fail, but the model usually recovers and still returns a complete response. These markers are only fatal when no valid response exists.

The `--from-response --external-cli-engine agy-cli` command enforces this split via `validate_agy_cli_run` in `cli_workflow/agy.py` (`AGY_CLI_HARD_FATAL_MARKERS` vs `AGY_CLI_RECOVERABLE_MARKERS`).

## Batches

For multiple papers, prepare sequentially, then run up to the selected worker
limit concurrently using the same resolved model and distinct output/stderr/log
paths. Apply responses sequentially. PDF preparation retains the compatibility
settings behavior; managed pure-link batches instead pass the model per run with
`agy --model` and never mutate shared settings.

### Parallel Batch Guidelines (When User Requests)

1. **Preconditions:** All papers must use the same Agy model; verify `agy_model_label` is identical across all prepared JSONs. Default to four workers and allow 1-8.
2. **Working directory:** Stay in `paperhub_utils/` throughout. Set `PAPERHUB_ROOT=$(cd .. && pwd)` once at the start.
3. **File isolation:** Each paper needs distinct temp files:
   - `prepare_N.json` (prepared input)
   - `/tmp/paperhub_agy_output_N.txt` (Agy stdout)
   - `/tmp/paperhub_agy_stderr_N.txt` (Agy stderr)
   - `/tmp/paperhub_agy_log_N.log` (Agy log file)
4. **Agy calls:** Use `agy --add-dir "$PAPERHUB_ROOT"` (variable ensures portability across machines).
5. **Wait synchronization:** Use `wait` to block until all background Agy processes complete before starting response processing phase.
6. **Error handling:** If any Agy call fails, report which paper(s) failed and ask user whether to retry, abandon, or switch models — never auto-recover.

## Error Handling

If Agy fails, ask the user whether to retry Agy, switch to OpenRouter, choose a different allowed Agy model, or abandon the paper. Never silently switch engines or models.

For parse failures, `uv run python -m scripts.paper_organizer --from-response` saves raw content under `paperhub_utils/output/raw_outputs/`. Do not manually rewrite the response with agent tokens. Ask before doing an AI format-repair retry.

## Completion Reporting

In `full` mode, `ai_summary.md` frontmatter should show:

```yaml
---
model: <model> (Agy CLI)
pdf_engine: agy-native
tokens_prompt: N/A
tokens_completion: N/A
total_tokens: N/A
cost: N/A
generated: 2026-05-24 14:30:00
---
```

In reports, say token usage is unavailable from Agy CLI and show `Cost: N/A`.
