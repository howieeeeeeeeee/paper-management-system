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
CODEX_CONFIG="$WORK/config.sh"
CODEX_OUTPUT="$WORK/output.txt"
CODEX_STDERR="$WORK/stderr.txt"

# 1. Prepare prompt/PDF and resolve the configured Codex model/reasoning pair.
#    --emit-shell also writes a sourceable config file. It refuses to write
#    unless every required field is non-empty, so sourcing it is the guard.
uv run python -m scripts.paper_organizer --prepare-cli-input \
  --external-cli-engine codex-cli \
  --pdf-path-arg "$PAPERHUB_ROOT/to_be_organized/paper.pdf" \
  --summary-mode full \
  --emit-shell "$CODEX_CONFIG" \
  > "$CODEX_INPUT"
```

Use `--summary-mode metadata-only` for metadata-only mode.

Add `--codex-model "MODEL_ID"` and/or `--codex-reasoning-effort "EFFORT"` only when the user explicitly requests a different allowed model/thinking pair (validated against `config.CODEX_CLI_MODEL_REASONING_PAIRS`). If unspecified, `--prepare-cli-input` resolves the configured default and writes it into the prepared JSON.

```bash
# 2. Call Codex (still in paperhub_utils/).
#    Source the generated config; never hand-extract fields. `|| exit 1` is
#    required - see Run Integrity item 6.
source "$CODEX_CONFIG" || exit 1
PROMPT=$(cat "$PROMPT_PATH")

codex exec \
  --cd "$PAPERHUB_ROOT" \
  --dangerously-bypass-approvals-and-sandbox \
  --ephemeral \
  --model "$MODEL" \
  -c "model_reasoning_effort=\"${EFFORT}\"" \
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
  < /dev/null 2>"${CODEX_STDERR}" > "${CODEX_OUTPUT}"
```

`< /dev/null` is required, not cosmetic — see Run Integrity item 5.

```bash
# 3. Organize from raw Codex output (still in paperhub_utils/).
#    Confirm this run wrote the response before applying it.
[ -s "$CODEX_OUTPUT" ] && [ "$CODEX_OUTPUT" -nt "$CODEX_INPUT" ] || echo "STALE OR EMPTY - do not apply"

# ORIGINAL_PDF, SUMMARY_MODE, MODEL_LABEL and CLEANUP_DIR already came from
# the sourced config in step 2 - do not re-extract them.
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
uv run python -m scripts.paper_organizer --cleanup-cli-input "${CLEANUP_DIR}"
rm -rf "$WORK"
```

## Validation Guards

Hard-fatal — do **not** organize output:

- Codex stdout is missing `PAPERHUB_RESPONSE_BEGIN` or `PAPERHUB_RESPONSE_END`, or the response block is empty.
- Codex stderr indicates authentication, rate-limit, permission, or file-read failures.
- A shutdown-only `codex_core::shell_snapshot` warning that says Codex could not
  delete an already-missing snapshot is ignored; it occurs after a successful
  response and is unrelated to reading the paper.
- Codex stderr is **empty**. A real run always writes progress output, so an empty stderr means Codex never ran and the response file is stale.
- The title in the response does not appear in the PDF, which means the response came from a different paper. When `pypdf` returns a corrupt text layer, the check automatically tries the optional local `pdftotext` command before rejecting the response.

Not fatal, and not a model failure — diagnose before retrying:

- Codex stderr is only `Reading additional input from stdin...` (or ends there) with empty stdout, and the process never exits. Stdin was left open; Codex is waiting to append it to the prompt. Kill it and re-run the **same** model with `< /dev/null` (Run Integrity item 5). Do not switch models or engines, and do not enter the failed-paper recovery flow — nothing was wrong with the request.
- Stdout is empty and stderr holds real progress output (often pages of extracted
  PDF text), with no sentinels and a kill/timeout exit code. The calling harness
  timed out, not Codex. A full-summary paper at a high reasoning effort routinely
  needs several minutes, and a parallel batch needs longer, so a default ~2 minute
  agent tool timeout will cut it off mid-reasoning. Re-run the **same** paper and
  model with the tool timeout raised to its maximum, or start the call in the
  background and poll. Do not switch models or engines.

The `--from-response --external-cli-engine codex-cli` command enforces these via `validate_codex_cli_run` in `cli_workflow/codex.py` and `title_mismatch_problem` in `cli_workflow/pdf.py`. The title check reads the PDF locally **after** Codex has already returned; it never preprocesses the PDF or changes what Codex receives, which is still the absolute PDF path.

**Never satisfy a guard by creating, blanking, or substituting an artifact file.** If `--from-response` reports a missing or empty stderr, Codex did not run — re-run it. Treating the guard as an obstacle silently organizes the wrong paper.

## Run Integrity (required before applying any response)

The generation step and the apply step are separate commands, so a failed generation can leave an old response file in place and the apply step will happily consume it. Guard against that:

1. **Use a fresh, unique artifact directory per batch** (for example `mktemp -d`), never fixed paths like `/tmp/paperhub_codex_output_1.txt`. Reused names are how a stale file from a previous session gets applied to a new PDF.
2. **Check each Codex call's own exit code.** A wrapper such as `for ... & done; wait` returns 0 even when every job inside it failed, so it proves nothing.
3. **Confirm the response file was written by this run** — non-empty, and newer than the prepared JSON.
4. **Never pass the prompt through a shell string.** The prompt contains backticks and `$`, which break shell quoting and can kill the command before Codex starts. Write the prompt to a file and read it in the language driving the call, or pass it as a direct argument in an argument list (for example `subprocess.run([...])`), not inside a generated `.sh` file.
5. **Always redirect stdin from `/dev/null`.** Per `codex exec --help`, when a prompt argument is given *and* stdin is piped, Codex appends stdin to the prompt as a `<stdin>` block — so it blocks until stdin reaches EOF. Agent tool calls, background jobs, and CI steps hand the child an open stdin that never closes, so the run hangs indefinitely instead of failing fast. Adding `< /dev/null` closes it. Do **not** "fix" this by piping the prompt in (`echo "$PROMPT" | codex exec`): that works only by accident, violates item 4, and `echo` mangles backslashes in some shells.
6. **Get the run's fields by sourcing `--emit-shell` output. Never hand-extract them.** `--emit-shell` validates every required field and refuses to write a partial file, so `source "$CODEX_CONFIG" || exit 1` cannot leave a variable empty. Hand-extraction can, silently: a mistyped `$WORK`, a renamed JSON key, or a swallowed `2>/dev/null` all yield an empty string, and `codex exec` is then invoked with an empty flag. An empty `EFFORT` fails loudly (`reasoning_effort must not be empty`), but an empty `PDF_PATH` does **not** — Codex starts normally with a blank path under full-access mode in `PAPERHUB_ROOT` and can summarize the wrong file. `title_mismatch_problem` catches that only at apply time, after a full reasoning run has been paid for. Do **not** try to guard hand-extraction with `set -e`: in `local x=$(cmd)` the `local` builtin's own exit status replaces the command substitution's, so a failing extraction reports success and `set -e` never fires. Plain `x=$(cmd)` preserves `$?`, but nothing checks it by default. Sourcing a validated file removes the whole class.

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

Give each paper its own `--emit-shell` config (`$WORK/config_N.sh`) and keep
every artifact for a paper — prepared JSON, config, stdout, stderr — under one
`$WORK` for the whole batch. Splitting them across directories is what makes a
path typo produce empty variables for some papers and not others.

Batches make the stale-artifact risk worse, because one broken job is easy to
miss among several that look fine. Apply the **Run Integrity** checks per paper
and report each paper's own result (exit code, bytes written, sentinels found)
before applying anything. Never apply a batch on the strength of the wrapper
command's exit code alone.

### Resume a stopped batch

The batch artifact directory is the resume record. Keep it until every paper is
applied or explicitly abandoned. After a checkpoint, do not regenerate a paper
whose own exit code is zero and whose prepared JSON, config, nonempty fresh
response, stderr, and single complete sentinel block are still present. Re-run
that paper's normal `--from-response` command so the validator and PDF-title
check run again, then continue applying the remaining responses sequentially.
Generate only papers without a complete valid artifact set. Clean the prepared
input and batch directory only after the batch is fully resolved.

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
