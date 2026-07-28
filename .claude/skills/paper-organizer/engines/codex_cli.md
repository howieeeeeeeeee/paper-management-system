# Workflow: Codex CLI

This document covers the **OpenAI Codex CLI** paper summarization workflow. Read this file when the user requests "codex cli", "use codex cli", or a direct OpenAI CLI workflow.

## Prerequisites

- `codex` CLI installed and authenticated.
- The default PaperHub Codex model/reasoning pair is configured in `paperhub_utils/config/config.json` (`codex_cli_model`, `codex_cli_reasoning_effort`) and resolved by `paperhub/config.py` as `config.CODEX_CLI_MODEL` and `config.CODEX_CLI_REASONING_EFFORT`. This doc does not name a default pair — read it from config, or from the prepared JSON, which carries the resolved values.
- The allowed model/reasoning pairs are defined in `config.CODEX_CLI_MODEL_REASONING_PAIRS` (`paperhub/config.py`). Treat that constant as the single source of truth; do not enumerate the pairs here. `--prepare-cli-input` validates the selection against it and rejects unsupported pairs.
- If the user requests a different allowed Codex model or thinking level, pass `--codex-model "MODEL_ID"` and/or `--codex-reasoning-effort "EFFORT"` to `--prepare-cli-input`.
- Codex exposes per-run model selection as `codex exec --model MODEL` / `-m MODEL`. Thinking level is passed as a per-run config override: `-c "model_reasoning_effort=\"${CODEX_REASONING_EFFORT}\""`. PaperHub does not write Codex global settings.
- PaperHub's Codex workflow uses local yolo/full-access mode by default (`codex_cli_yolo: true`) for smooth local-folder runs. `--cd "$PAPERHUB_ROOT"` sets the working root, but yolo removes OS-level sandboxing; keep this for trusted PaperHub folders only.
- The standard workflow captures the final Codex message, not JSONL events. Record model as `<model> (<effort> reasoning) (Codex CLI)`, `pdf_engine: codex-cli`, and token fields as `N/A` unless you explicitly run `codex exec --json` and pass token counts to `--from-response`.

## Overview

This workflow reuses the same prompt and file-organization logic as the OpenRouter and Agy workflows:

1. Call `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine codex-cli` to prepare the prompt/PDF and resolve the selected Codex model/reasoning pair.
2. Call `codex exec` with `--cd "$PAPERHUB_ROOT"`, `--dangerously-bypass-approvals-and-sandbox`, `--model "$CODEX_MODEL"`, and `-c "model_reasoning_effort=\"${CODEX_REASONING_EFFORT}\""`.
3. Save Codex final output and stderr files.
4. Call `uv run python -m scripts.paper_organizer --from-response --external-cli-engine codex-cli`; the script validates Codex artifacts, extracts the sentinel-delimited response block, and organizes the paper.

In `metadata-only` mode, `--prepare-cli-input` creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF under `.paperhub_tmp/`; Codex receives that temporary PDF path, while `--from-response` still moves the original PDF into `organized/`.

**Critical Codex path rule:** Always run the PaperHub preparation/apply commands from `paperhub_utils/`. Set `PAPERHUB_ROOT=$(cd .. && pwd)` first, then run `codex exec --cd "$PAPERHUB_ROOT"` with the absolute PDF path from `pdf_for_ai_codex_path`.

## Mode Mapping

| PaperHub mode | Prepare command | Apply command | Output |
|---|---|---|---|
| `full` | `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine codex-cli --summary-mode full` | `uv run python -m scripts.paper_organizer --from-response --external-cli-engine codex-cli --summary-mode full` | metadata note + `ai_summary.md` |
| `metadata-only` | `uv run python -m scripts.paper_organizer --prepare-cli-input --external-cli-engine codex-cli --summary-mode metadata-only` | `uv run python -m scripts.paper_organizer --from-response --external-cli-engine codex-cli --summary-mode metadata-only` | metadata note only; no `ai_summary.md` |
| `enrich` | `uv run python -m scripts.enrich --engine codex-cli --prepare-cli-input --folder FOLDER` | `uv run python -m scripts.enrich --engine codex-cli --from-response --folder FOLDER` | existing folder patched and/or `ai_summary.md` written |

Use the same Codex call shape for all three modes: read `prompt_path`, `pdf_for_ai_codex_path`, `paperhub_root`, `codex_cli_model`, `codex_cli_reasoning_effort`, `codex_cli_yolo`, and `codex_model_label` from the prepared JSON, then pass raw output to the matching `--from-response` command.

## Full Or Metadata-Only Paper

```bash
# From paperhub_utils/
cd paperhub_utils
PAPERHUB_ROOT=$(cd .. && pwd)

# 0. Fresh per-run artifact directory. Never reuse fixed names — see Run
#    Integrity below. Every artifact path derives from $WORK.
WORK=$(mktemp -d)
CODEX_INPUT="$WORK/input.json"
CODEX_OUTPUT="$WORK/output.txt"
CODEX_STDERR="$WORK/stderr.txt"

# 1. Prepare prompt/PDF and resolve the configured Codex model/reasoning pair.
uv run python -m scripts.paper_organizer --prepare-cli-input \
  --external-cli-engine codex-cli \
  --pdf-path-arg "$PAPERHUB_ROOT/to_be_organized/paper.pdf" \
  --summary-mode full \
  > "$CODEX_INPUT"
```

Use `--summary-mode metadata-only` for metadata-only mode.

Add `--codex-model "MODEL_ID"` and/or `--codex-reasoning-effort "EFFORT"` only when the user explicitly requests a different allowed model/thinking pair (validated against `config.CODEX_CLI_MODEL_REASONING_PAIRS`). If unspecified, `--prepare-cli-input` resolves the configured default and writes it into the prepared JSON.

```bash
# 2. Call Codex (still in paperhub_utils/).
read_field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$CODEX_INPUT" "$1"; }
PROMPT=$(python3 -c "import json,sys; print(open(json.load(open(sys.argv[1]))['prompt_path']).read())" "$CODEX_INPUT")
PDF_PATH=$(read_field pdf_for_ai_codex_path)
CODEX_MODEL=$(read_field codex_cli_model)
CODEX_REASONING_EFFORT=$(read_field codex_cli_reasoning_effort)

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
#    Confirm this run wrote the response before applying it.
[ -s "$CODEX_OUTPUT" ] && [ "$CODEX_OUTPUT" -nt "$CODEX_INPUT" ] || echo "STALE OR EMPTY - do not apply"

ORIGINAL_PDF=$(read_field original_pdf_path)
SUMMARY_MODE=$(read_field summary_mode)
MODEL_LABEL=$(read_field codex_model_label)

uv run python -m scripts.paper_organizer --from-response \
  --external-cli-engine codex-cli \
  --response-file "${CODEX_OUTPUT}" \
  --pdf-path-arg "${ORIGINAL_PDF}" \
  --summary-mode "${SUMMARY_MODE}" \
  --model-label "${MODEL_LABEL}" \
  --codex-stderr-file "${CODEX_STDERR}"
```

```bash
# 4. Clean up prepared prompt/temp PDF, then the artifact directory.
CLEANUP_DIR=$(read_field cleanup_dir)
uv run python -m scripts.paper_organizer --cleanup-cli-input "${CLEANUP_DIR}"
rm -rf "$WORK"
```

## Validation Guards

Hard-fatal — do **not** organize output:

- Codex stdout is missing `PAPERHUB_RESPONSE_BEGIN` or `PAPERHUB_RESPONSE_END`, or the response block is empty.
- Codex stderr indicates authentication, rate-limit, permission, or file-read failures.
- Codex stderr is **empty**. A real run always writes progress output, so an empty stderr means Codex never ran and the response file is stale.
- The title in the response does not appear in the PDF, which means the response came from a different paper.

The `--from-response --external-cli-engine codex-cli` command enforces these via `validate_codex_cli_run` in `cli_workflow/codex.py` and `title_mismatch_problem` in `cli_workflow/pdf.py`. The title check reads the PDF locally **after** Codex has already returned; it never preprocesses the PDF or changes what Codex receives, which is still the absolute PDF path.

**Never satisfy a guard by creating, blanking, or substituting an artifact file.** If `--from-response` reports a missing or empty stderr, Codex did not run — re-run it. Treating the guard as an obstacle silently organizes the wrong paper.

## Run Integrity (required before applying any response)

The generation step and the apply step are separate commands, so a failed generation can leave an old response file in place and the apply step will happily consume it. Guard against that:

1. **Use a fresh, unique artifact directory per batch** (for example `mktemp -d`), never fixed paths like `/tmp/paperhub_codex_output_1.txt`. Reused names are how a stale file from a previous session gets applied to a new PDF.
2. **Check each Codex call's own exit code.** A wrapper such as `for ... & done; wait` returns 0 even when every job inside it failed, so it proves nothing.
3. **Confirm the response file was written by this run** — non-empty, and newer than the prepared JSON.
4. **Never pass the prompt through a shell string.** The prompt contains backticks and `$`, which break shell quoting and can kill the command before Codex starts. Write the prompt to a file and read it in the language driving the call, or pass it as a direct argument in an argument list (for example `subprocess.run([...])`), not inside a generated `.sh` file.

If any check fails, treat the paper as failed and follow **Error Handling** below.

## Reasoning And Yolo Settings

- Set the default model in `paperhub_utils/config/config.json` with `codex_cli_model`.
- Set the default thinking level with `codex_cli_reasoning_effort`. Allowed model/effort combinations are enforced against `config.CODEX_CLI_MODEL_REASONING_PAIRS` (`paperhub/config.py`).
- Set `codex_cli_yolo` to `true` for the local full-access flow. The command starts Codex in the PaperHub root with `--cd "$PAPERHUB_ROOT"`, disables web search with `-c 'web_search="disabled"'`, and instructs Codex not to edit files. Yolo/full-access itself is not an OS-level folder restriction.
- If the user wants sandboxed Codex runs later, set `codex_cli_yolo` to `false` and replace `--dangerously-bypass-approvals-and-sandbox` with `--sandbox read-only -c 'approval_policy="never"'` in the command shape.

## Batches

For multiple papers, prepare sequentially, then run up to the selected worker
limit concurrently using the same resolved model/reasoning pair and distinct
output/stderr paths. Default to four workers and allow 1-8. Wait for every
scheduled generation call, then apply responses sequentially so output folders
and duplicate checks cannot race.

Batches make the stale-artifact risk worse, because one broken job is easy to
miss among several that look fine. Apply the **Run Integrity** checks per paper
and report each paper's own result (exit code, bytes written, sentinels found)
before applying anything. Never apply a batch on the strength of the wrapper
command's exit code alone.

## Error Handling

If Codex fails, ask the user whether to retry Codex, switch to OpenRouter, choose a different allowed Codex model/reasoning pair, or abandon the paper. Never silently switch engines or models.

For parse failures, `uv run python -m scripts.paper_organizer --from-response` saves raw content under `paperhub_utils/output/raw_outputs/`. Do not manually rewrite the response with agent tokens. Ask before doing an AI format-repair retry.

## Completion Reporting

In `full` mode, `ai_summary.md` frontmatter should show:

```yaml
---
model: <model> (<effort> reasoning) (Codex CLI)
pdf_engine: codex-cli
tokens_prompt: N/A
tokens_completion: N/A
total_tokens: N/A
cost: N/A
generated: 2026-06-22 14:30:00
---
```

In reports, say token usage is unavailable from the standard Codex CLI flow and show `Cost: N/A`.
