# Workflow: OpenRouter Script

This document covers the **default** paper summarization workflow using `paper_summarizer.py` via the OpenRouter API. Read this file when the user does NOT request Gemini CLI.

## Script Location

```
paperhub_utils/paper_summarizer.py
```

**Working directory:** `paperhub_utils/` (has uv environment)

## How the Script Works

1. **PDF Encoding**: PDF is read and encoded to base64 for API transmission
2. **Prompt Construction**: Composes the prompt from `prompt/shared/` and `prompt/aspect/` fragments via `prompt/builder.py` and fills in dynamic values (date, research interests, user instructions)
3. **API Call**: Sends PDF (base64) + prompt to OpenRouter with `file-parser` plugin using `mistral-ocr` engine
4. **Response Parsing**: Parses markdown sections (`# paper_label`, `# metadata`, plus `# ai_summary` in `full` mode), falls back to JSON
5. **Output Generation**: Creates folder, writes metadata, writes summary in `full` mode, moves original PDF
6. **Returns JSON** with per-paper status, token usage, and file paths

In `metadata-only` mode, the script creates a temporary first-`METADATA_ONLY_PAGE_LIMIT` PDF, sends only that temporary PDF to OpenRouter, writes metadata only, deletes the temporary PDF, and moves the original PDF into `organized/`.

## Calling the Script

**Single PDF:**

```bash
cd paperhub_utils
uv run python paper_summarizer.py "../to_be_organized/paper.pdf"
```

**Single PDF, metadata only:**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper.pdf" --summary-mode metadata-only
```

**Multiple PDFs (script processes in parallel, max 4 workers):**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper1.pdf" "../to_be_organized/paper2.pdf" "../to_be_organized/paper3.pdf"
```

Pass the same `--summary-mode` once for the whole batch.

**With custom model:**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper.pdf" --model "anthropic/claude-sonnet-4"
```

**With additional instructions (user-provided context):**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper.pdf" --instruction "Focus on the identification strategy and data sources"
```

**With explicit full-summary mode:**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper.pdf" --summary-mode full
```

**With verbose logging:**

```bash
uv run python paper_summarizer.py "../to_be_organized/paper.pdf" --verbose
```

**Note on `--instruction`:** If the user provides any additional context, notes, or specific requests in their message (e.g., "this paper is about X", "pay attention to the welfare analysis"), pass it via the `--instruction` flag. Omit the flag if the user provides no extra info.

## Script Output Format

The script outputs JSON to stdout:

**Success output:**

```json
{
  "success": true,
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "results": [
    {
      "success": true,
      "paper_label": "melitz2003trade",
      "output_dir": "organized/melitz2003trade/",
      "files_created": ["melitz2003trade.md", "ai_summary.md"],
      "summary_mode": "full",
      "pdf_moved": true,
      "pdf_path": "organized/melitz2003trade/melitz_2003.pdf",
      "usage": {"prompt_tokens": 50000, "completion_tokens": 8000, "total_tokens": 58000, "cost": 0.23}
    }
  ]
}
```

**Partial failure output:**

```json
{
  "success": false,
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"success": true, "paper_label": "melitz2003trade", ...},
    {"success": true, "paper_label": "card1994wages", ...},
    {"success": false, "pdf_path": "to_be_organized/corrupted.pdf", "error": "API call failed after all retries"}
  ]
}
```

Always extract and report token usage from each result's `usage` field: `prompt_tokens`, `completion_tokens`, `total_tokens`.

In `metadata-only` mode, `files_created` contains only `{paper_label}.md`; do not expect `ai_summary.md`.

The metadata file must include `contributions:` as an empty YAML field and a `## Abstract` section with the paper abstract copied verbatim when present.

## Model Selection

The default model is configured in `config.py` as `DEFAULT_MODEL`. The full list of available models is in `config.py`'s `MODEL_LIST`.

**ONLY use model IDs from `MODEL_LIST` — never guess or invent an ID.**

To check current defaults:

```
paperhub_utils/config.py
```

Override with `--model` flag (e.g., `--model "xxx"`). The script looks up the provider order from `MODEL_LIST` automatically.

## Handling Partial Failures

1. Check `failed` count — if > 0, some papers failed
2. Extract failed papers from `results` where `success: false`
3. Report the failure summary to the user
4. Use **`AskUserQuestion`** tool:

   **Question 1 — Action:**
   - Header: "Failed papers"
   - Question: "{N} paper(s) failed. What would you like to do?"
   - Options:
     - "Abandon" — Skip failed papers, commit successful ones
     - "Retry" — Retry with the same model
     - "Try a different model" — Retry with a different model

   **If "Try a different model" → Question 2 — Model selection:**
   - Header: "Model"
   - Question: "Which model would you like to use?"
   - Read `config.py`'s `MODEL_LIST` and present `model_id` values as options

   **NEVER present a model not in `config.py`'s `MODEL_LIST`.**

## Error Handling

### API Failure

Print error summary, then use **`AskUserQuestion`**:

- Question: "The API call failed. What would you like to do?"
- Options: "Abandon", "Retry (same model)", "Try a different model"

### DeepSeek V3.2 Empty Response (Known Issue)

DeepSeek V3.2 sometimes returns `response_length: 0` with all tokens consumed as `reasoning_tokens`. Retry once automatically. If it fails again, use **`AskUserQuestion`** (Abandon / Retry / Different model).

### Parse Failure with Raw Content Fallback

When API succeeds but parsing fails, the script saves raw content to `raw_outputs/`.

**Result JSON includes:** `error_type: "ParseError"` and `raw_content_file: "paperhub_utils/raw_outputs/filename.md"`

**Fallback workflow:**

1. Check if result has `raw_content_file`
2. Read the raw file (has YAML frontmatter with `pdf_path`, token usage)
3. Extract sections according to the selected mode: `full` expects metadata plus `# ai_summary`; `metadata-only` expects metadata only
4. Create folder under organized/, write `{label}.md`, write `ai_summary.md` only in `full` mode, move PDF
5. Clean up: `uv run python paper_summarizer.py --delete-raw "raw_outputs/raw_file.md"`
6. Commit and report as usual

## Batch Processing Logic

1. **Collect PDF paths** — Gather all PDF file paths
2. **Single script call** — Pass all paths to the script in one command (handles parallel processing internally, max 4 workers)
3. **Parse results** — Check each paper's status in the `results` array
4. **Handle failures** — Retry or ask user
5. **Validate & fix** — Check output files, auto-fix issues (see shared rules in SKILL.md; summary file check is `full` mode only)
6. **Batch commit** — Commit all successful papers together
