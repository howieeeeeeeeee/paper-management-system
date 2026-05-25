# Workflow: Gemini CLI

> Legacy note: Gemini CLI is no longer the active direct-Google CLI workflow for PaperHub. Use `engines/agy_cli.md` for new requests. Keep this document only as a reference in case legacy Gemini CLI support is explicitly requested or restored later.

This document covers the **Gemini CLI** paper summarization workflow. Read this file when the user requests processing "with gemini cli" or is routed here via the disambiguation flow.

## Prerequisites

- `gemini` CLI installed and authenticated (user's Google account)
- The Gemini CLI uses Google's free-tier API — no cost tracking available
- The Gemini model is configured in `paperhub_utils/config.py` as
  `GEMINI_CLI_MODEL` (loaded from `misc/config.json` key `gemini_cli_model`,
  default `gemini-3.1-pro-preview`). Read it once at the top of any Gemini-CLI
  shell flow and reuse the variable — never hardcode the model name in this
  skill:

  ```bash
  GEMINI_MODEL=$(cd paperhub_utils && uv run python -c "from config import GEMINI_CLI_MODEL; print(GEMINI_CLI_MODEL)")
  ```

- If Gemini is not authenticated, run a tiny TTY auth check before processing a
  paper:

  ```bash
  # Run from the paper-library root.
  gemini --skip-trust -p "Reply with exactly: auth-ok" \
    -m "${GEMINI_MODEL}" -o json
  ```

  Answer `Y` if Gemini asks to open an authentication page, then complete the
  browser login. In Codex, this command may need `require_escalated` because
  Gemini OAuth starts a local callback server; sandboxed runs can fail with
  `listen EPERM: operation not permitted 0.0.0.0`.

## Overview

Instead of using the Python script's OpenRouter API pipeline, this workflow:

1. Calls `paper_summarizer.py --prepare-cli-input` to prepare the prompt and Gemini-readable PDF path
2. Calls `gemini` CLI directly via Bash to send the PDF + prompt to Gemini
3. Extracts the AI response and token stats from JSON output
4. Calls `paper_summarizer.py --from-response` to handle file organization (folder creation, PDF move, metadata/summary writing)

This reuses the same prompt template and file-organization logic as the script workflow.

In `metadata-only` mode, `--prepare-cli-input` creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF under `.paperhub_tmp/` so Gemini CLI can read it from the repo workspace. `--from-response` still receives the original PDF path and moves the original PDF into `organized/`.

**Critical Gemini CLI path rule:** run `gemini` from the paper-library root and reference PDFs with root-relative `@path` syntax. Do **not** run Gemini from `paperhub_utils/`; that puts the PDF outside Gemini CLI's expected workspace. Do **not** use `@"absolute path"` quoting. If a root-relative PDF path contains spaces, escape spaces with backslashes.

## Step-by-Step

### Step 1 & 2: Prepare Prompt and PDF Input

Use the script helper to generate the filled prompt and choose the PDF that Gemini should read:

```bash
cd paperhub_utils
uv run python paper_summarizer.py --prepare-cli-input \
  --pdf-path-arg "../to_be_organized/paper.pdf" \
  --summary-mode full \
  --instruction "USER_INSTRUCTION_HERE_OR_EMPTY" \
  > /tmp/paperhub_gemini_input.json
```

Use `--summary-mode metadata-only` for metadata-only batches. Replace `USER_INSTRUCTION_HERE_OR_EMPTY` with the user's additional instructions, or omit `--instruction` if none.

### Step 3: Call Gemini CLI

Read the prepared prompt path and repo-relative PDF path from the helper JSON, then call Gemini CLI:

```bash
# Run from the paper-library root.

PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_gemini_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['pdf_for_ai_gemini_path'])")

gemini --skip-trust -y -p "@${PDF_PATH}

Use only the attached PDF. Do not use web search. Do not infer from the filename.

${PROMPT}" -m "${GEMINI_MODEL}" -o json 2>/tmp/gemini_stderr.txt > /tmp/gemini_output.json
```

**Important notes:**

- Run `gemini` from the paper-library root, not from `paperhub_utils/`.
- In Codex, run Gemini with escalation if authentication or the paper call needs
  to bind the local OAuth callback port. A sandbox failure looks like
  `listen EPERM: operation not permitted 0.0.0.0`.
- If `/tmp/gemini_output.json` contains
  `Opening authentication page in your browser. Do you want to continue? [Y/n]:`,
  it is not JSON and the model did not run. Authenticate with the tiny TTY check
  above, then rerun the paper call.
- The `@filepath` syntax tells Gemini CLI to read the file. Put it at the START of the prompt, before a blank line and the prompt text.
- Use repo-relative paths, e.g. `@organized/label/paper.pdf` or
  `@to_be_organized/devil.pdf`.
- In `metadata-only` mode, the repo-relative path points under `.paperhub_tmp/`.
- Do not quote the path as `@"..."`. For spaces inside the repo-relative path, escape spaces with backslashes.
- Use `-o json` to get structured output with token stats.
- Model: read from `config.GEMINI_CLI_MODEL` (see Prerequisites). To switch to a different Gemini model, edit `gemini_cli_model` in `paperhub_utils/misc/config.json`.
- The command may take 1-5 minutes for large PDFs — this is normal. Use a **10-minute timeout** (`timeout: 600000`).
- Redirect stderr to a file to capture errors separately.

### Step 3b: Verify Gemini Read the PDF

Before organizing output, inspect the Gemini artifacts. The `--from-response` command enforces this via `cli_workflow/gemini.py`. Treat these as fatal and do **not** organize the response:

- stderr contains `Path not in workspace`
- stderr contains `No valid file paths`
- stderr contains `Error executing tool read_file`
- stderr contains `file read failed` or `file access failed`
- JSON stats show failed `read_file` or `read_many_files` calls
- JSON stats show `google_web_search` calls

These indicate Gemini did not rely on the attached PDF and may have inferred content from the filename or web search.

### Step 4: Parse Gemini CLI Output

The JSON output has this structure:

```json
{
  "session_id": "...",
  "response": "<AI response text>",
  "stats": {
    "models": {
      "gemini-3.1-pro": {
        "tokens": {
          "prompt": 4713,
          "candidates": 1200,
          "total": 6413,
          "cached": 4000,
          "thoughts": 500
        }
      }
    }
  }
}
```

Extract:

- **Response text**: `response` field — this is the AI-generated paper analysis
- **Token stats**: from `stats.models.<model_name>.tokens`:
  - `prompt` → prompt tokens
  - `candidates` → completion tokens
  - `thoughts` → thinking tokens
  - `cached` → cached tokens
  - `total` → total tokens

### Step 5: Save Response and Call Script

1. **Save** the response text to a temp file:

   ```bash
   # Write response text to temp file (use python to extract from JSON)
   ```

2. **Call script** in `--from-response` mode:

   ```bash
   cd paperhub_utils
   ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['original_pdf_path'])")
   SUMMARY_MODE=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['summary_mode'])")
   uv run python paper_summarizer.py --from-response \
     --response-file "/tmp/paperhub_gemini_<timestamp>.txt" \
     --pdf-path-arg "${ORIGINAL_PDF}" \
     --summary-mode "${SUMMARY_MODE}" \
     --model-label "${GEMINI_MODEL} (Gemini CLI)" \
     --gemini-stderr-file "/tmp/gemini_stderr.txt" \
     --gemini-output-json "/tmp/gemini_output.json" \
     --tokens-prompt <prompt> \
     --tokens-completion <candidates> \
     --tokens-thinking <thoughts> \
     --tokens-cached <cached> \
     --tokens-total <total>
   ```

3. **Parse script output** — same JSON format as the normal workflow.

4. **Clean up prepared prompt/temp PDF:**

   ```bash
   CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['cleanup_dir'])")
   uv run python paper_summarizer.py --cleanup-cli-input "${CLEANUP_DIR}"
   ```

### Step 6: Continue with Shared Steps

After the script returns, follow the shared validation, auto-fix, git commit, and reporting steps in SKILL.md.

## Practical Example: Single Paper

```bash
# 0. Read the configured Gemini model once
GEMINI_MODEL=$(cd paperhub_utils && uv run python -c "from config import GEMINI_CLI_MODEL; print(GEMINI_CLI_MODEL)")

# 1. Prepare prompt and Gemini-readable PDF
cd paperhub_utils
uv run python paper_summarizer.py --prepare-cli-input \
  --pdf-path-arg "../to_be_organized/melitz_2003.pdf" \
  --summary-mode full \
  > /tmp/paperhub_gemini_input.json

# 2. Call Gemini CLI
cd ..
PROMPT=$(python3 -c "import json; print(open(json.load(open('/tmp/paperhub_gemini_input.json'))['prompt_path']).read())")
PDF_PATH=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['pdf_for_ai_gemini_path'])")
gemini --skip-trust -y -p "@${PDF_PATH}

Use only the attached PDF. Do not use web search. Do not infer from the filename.

${PROMPT}" -m "${GEMINI_MODEL}" -o json 2>/tmp/gemini_stderr.txt > /tmp/gemini_output.json

# 3. Extract response text
python3 -c "import json; d=json.load(open('/tmp/gemini_output.json')); open('/tmp/gemini_response.txt','w').write(d['response'])"

# 4. Extract token stats and call script
python3 -c "
import json
d = json.load(open('/tmp/gemini_output.json'))
models = d.get('stats',{}).get('models',{})
model_name = list(models.keys())[0]
tokens = models[model_name].get('tokens',{})
print(f'--tokens-prompt {tokens.get(\"prompt\",0)}')
print(f'--tokens-completion {tokens.get(\"candidates\",0)}')
print(f'--tokens-thinking {tokens.get(\"thoughts\",0)}')
print(f'--tokens-cached {tokens.get(\"cached\",0)}')
print(f'--tokens-total {tokens.get(\"total\",0)}')
"
# Use the printed values in the --from-response call:

cd paperhub_utils
ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['original_pdf_path'])")
SUMMARY_MODE=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['summary_mode'])")
uv run python paper_summarizer.py --from-response \
  --response-file "/tmp/gemini_response.txt" \
  --pdf-path-arg "${ORIGINAL_PDF}" \
  --summary-mode "${SUMMARY_MODE}" \
  --model-label "${GEMINI_MODEL} (Gemini CLI)" \
  --gemini-stderr-file "/tmp/gemini_stderr.txt" \
  --gemini-output-json "/tmp/gemini_output.json" \
  --tokens-prompt 4713 --tokens-completion 1200 --tokens-total 6413

# 5. Clean up prepared prompt/temp PDF
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_gemini_input.json'))['cleanup_dir'])")
uv run python paper_summarizer.py --cleanup-cli-input "${CLEANUP_DIR}"
```

## Multiple Papers

### Parallel Batching (Recommended)

Process papers in **parallel batches of up to 3 papers** to optimize API quota and throughput. Larger batches may trigger rate limiting; smaller batches are safer but slower.

**Workflow:**

1. **Prepare inputs for all papers in a batch** (parallel is safe):
   ```bash
   for pdf in ../to_be_organized/paper1.pdf ../to_be_organized/paper2.pdf ../to_be_organized/paper3.pdf; do
     uv run python paper_summarizer.py --prepare-cli-input \
       --pdf-path-arg "$pdf" --summary-mode full > /tmp/paperhub_gemini_input_N.json &
   done
   wait  # Wait for all prepare calls to complete
   ```

2. **Call Gemini CLI for all papers in the batch in parallel** (run from repo root):
   ```bash
   for i in 1 2 3; do
     PROMPT=$(python3 -c "import json; print(open(json.load(open(\"/tmp/paperhub_gemini_input_$i.json\"))[\"prompt_path\"]).read())")
     PDF_PATH=$(python3 -c "import json; print(json.load(open(\"/tmp/paperhub_gemini_input_$i.json\"))[\"pdf_for_ai_gemini_path\"])")
     gemini --skip-trust -y -p "@${PDF_PATH}
   
   Use only the attached PDF. Do not use web search. Do not infer from the filename.
   
   ${PROMPT}" -m "${GEMINI_MODEL}" -o json 2>/tmp/gemini_stderr_$i.txt > /tmp/gemini_output_$i.json &
   done
   wait  # Wait for all Gemini calls to complete (up to 10 minutes)
   ```

3. **Extract responses and process in parallel** (extract responses):
   ```bash
   for i in 1 2 3; do
     python3 -c "import json; d=json.load(open(\"/tmp/gemini_output_$i.json\")); open(\"/tmp/gemini_response_$i.txt\",\"w\").write(d['response'])" &
   done
   wait
   ```

4. **Process responses sequentially** (organize files one at a time to avoid contention):
   ```bash
   for i in 1 2 3; do
     # Extract token stats
     python3 -c "
   import json
   d = json.load(open('/tmp/gemini_output_$i.json'))
   models = d.get('stats',{}).get('models',{})
   model_name = list(models.keys())[0]
   tokens = models[model_name].get('tokens',{})
   print(f'--tokens-prompt {tokens.get(\"prompt\",0)}')
   print(f'--tokens-completion {tokens.get(\"candidates\",0)}')
   print(f'--tokens-thinking {tokens.get(\"thoughts\",0)}')
   print(f'--tokens-cached {tokens.get(\"cached\",0)}')
   print(f'--tokens-total {tokens.get(\"total\",0)}')
   " > /tmp/tokens_$i.txt
     
     # Call --from-response
     TOKENS=$(cat /tmp/tokens_$i.txt | tr '\n' ' ')
     ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open(\"/tmp/paperhub_gemini_input_$i.json\"))[\"original_pdf_path\"])")
     SUMMARY_MODE=$(python3 -c "import json; print(json.load(open(\"/tmp/paperhub_gemini_input_$i.json\"))[\"summary_mode\"])")
     
     cd paperhub_utils
     uv run python paper_summarizer.py --from-response \
       --response-file "/tmp/gemini_response_$i.txt" \
       --pdf-path-arg "${ORIGINAL_PDF}" \
       --summary-mode "${SUMMARY_MODE}" \
       --model-label "${GEMINI_MODEL} (Gemini CLI)" \
       --gemini-stderr-file "/tmp/gemini_stderr_$i.txt" \
       --gemini-output-json "/tmp/gemini_output_$i.json" \
       ${TOKENS}
     cd ..
   done
   ```

5. **Clean up temp files for all papers**:
   ```bash
   for i in 1 2 3; do
     CLEANUP_DIR=$(python3 -c "import json; print(json.load(open(\"/tmp/paperhub_gemini_input_$i.json\"))[\"cleanup_dir\"])")
     cd paperhub_utils
     uv run python paper_summarizer.py --cleanup-cli-input "${CLEANUP_DIR}"
     cd ..
   done
   ```

6. Run tag classification, auto-fix, and commit (see `shared/post_ai.md` and `tags/post_summary_update.md`).

### Sequential Processing (Fallback)

If you encounter rate limiting with parallel batches, fall back to **sequential processing** (one Gemini CLI call per paper):

1. Run `--prepare-cli-input` with the batch summary mode
2. Call Gemini CLI
3. Save response and call `--from-response` with the same summary mode
4. Clean up `cleanup_dir`
5. Repeat for next paper

After all papers are processed, run tag classification, batch commit, and report.

## Error Handling

### Gemini CLI Failures (429, Capacity Errors)

If Gemini CLI fails with 429, RESOURCE_EXHAUSTED, MODEL_CAPACITY_EXHAUSTED, or any error, use **`AskUserQuestion`**:

- Header: "Gemini CLI error"
- Question: "Gemini CLI failed: [error message]. What would you like to do?"
- Options:
  1. "Retry with Gemini CLI" — retry the same command
  2. "Switch to OpenRouter (default model)" — fall back to the script workflow with default model from `config.py`
  3. "Switch to OpenRouter (choose model)" — show model picker from `config.py` `MODEL_LIST`
  4. "Abandon" — skip this paper

### Parse Errors

The `--from-response` script has deterministic CLI fallback parsers in `cli_workflow/utils.py` for responses that start with YAML metadata. In `full` mode it can parse metadata followed by `# ai_summary`; in `metadata-only` mode it can parse metadata-only output. Let the script normalize the response and continue the normal organization flow.

If parsing still fails, the script saves raw content to `raw_outputs/`. Do not manually rewrite the response with agent tokens. Ask the user before doing an AI format-repair retry. If approved, call Gemini CLI with the raw response text only and ask it to preserve every substantive word while converting the wrapper to the mode-appropriate format.

For `full` mode:

```markdown
# paper_label
[label only]

# metadata
[metadata markdown]

# ai_summary
[summary markdown]
```

For `metadata-only` mode:

```markdown
# paper_label
[label only]

# metadata
[metadata markdown]
```

Then pass the repaired response back to `paper_summarizer.py --from-response` with the same `--gemini-stderr-file` and `--gemini-output-json` guard files from the original PDF-reading run.

For every mode, metadata must include `contributions:` as an empty YAML field and a `## Abstract` section with the paper abstract copied verbatim when present.

## Token Reporting

In `full` mode, the `ai_summary.md` frontmatter will show:

```yaml
---
model: <GEMINI_CLI_MODEL> (Gemini CLI)
pdf_engine: gemini-native
tokens_prompt: 4713
tokens_completion: 1200
total_tokens: 6413
cost: N/A
generated: 2026-04-10 14:30:00
---
```

In the completion report, show:

```
Token usage: 4,713 prompt + 1,200 completion = 6,413 total (500 thinking, 4,000 cached)
Cost: N/A (Gemini CLI free tier)
```

**Note:** Gemini CLI does not report remaining quota or reset times.

In `metadata-only` mode there is no `ai_summary.md`; report token usage from the result JSON and the Gemini stats instead.
