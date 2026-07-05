# Workflow: Current Coding Agent

This workflow uses the **current coding-agent session** (you, right now) as the AI engine — no OpenRouter API, no Agy CLI. Use it when the user explicitly asks for the current coding agent / "use you" / "no external AI".

Supports all three modes: `metadata-only` (cheap), `full` (expensive), and `enrich` (expensive).

## Quota warning — read first

In `full` and `enrich` modes the agent reads the **entire PDF natively** with the `Read` tool and writes the summary in-session. A typical paper is 15-40 pages → roughly **50k-200k input tokens per paper** plus 5k-15k output tokens. Multiply by N papers. This burns the user's Claude Code session quota, not OpenRouter credit.

In `metadata-only` mode only the first `METADATA_ONLY_PAGE_LIMIT` pages are extracted as plain text via `pypdf`, so quota cost is small.

### Mandatory pre-flight gate (full / enrich only)

Before running `full` or `enrich` via this engine, you **MUST** confirm with the user via `AskUserQuestion`:

- Header: `High quota run`
- Question: `This will read N PDF(s) entirely in this session (~50k–200k tokens per paper). Cost is high. Proceed?`
- Options:
  - **Proceed** — run the coding-agent flow as requested
  - **Switch to OpenRouter** — re-route to `engines/openrouter.md` with the same mode and instruction
  - **Switch to metadata-only** *(only when the original mode was `full`)* — drop to the cheap path
  - **Cancel** — abandon

Skip the gate only when the user already explicitly opted in (e.g., "I know it's expensive, summarize it with you").

### Soft batch cap

For `full` and `enrich` via this engine, refuse more than **3 papers per invocation** without a second `AskUserQuestion` confirmation. Process the first 3 and ask again before continuing — never let a batch silently balloon.

## How this engine differs from OpenRouter / Agy CLI

| Step | OpenRouter / Agy CLI | Coding agent (this doc) |
|---|---|---|
| Build prompt | script reads `paperhub/prompt/builder.py` | same — call `--prepare-cli-input` |
| Read PDF | API plugin / Agy native | `Read` tool reads PDF directly |
| Generate content | API call | YOU generate it in this turn |
| Lay down files (full / metadata-only) | script `--from-response` | direct `Bash mkdir / mv` + `Write` |
| Lay down files (enrich) | script `--from-response` | script `--from-response` (merge logic is non-trivial) |
| Tag handoff, validation, commit | shared post-AI flow | shared post-AI flow (unchanged) |

The script is used for **prompt prep**, **enrich merge**, **cleanup**, and **tag handoff**. Everything else is direct file ops.

---

## Mode 1: metadata-only (cheap)

No quota gate needed. First-N-pages extraction → you write metadata only.

### Step 1 — read config

```bash
cd paperhub_utils
uv run python -c "from paperhub.config import METADATA_ONLY_PAGE_LIMIT, MY_RESEARCH_INTERESTS; print(METADATA_ONLY_PAGE_LIMIT); print('---'); print(MY_RESEARCH_INTERESTS)"
```

Use the page limit and research interests for the metadata draft. If `MY_RESEARCH_INTERESTS` is empty / placeholder, write `[To be filled]` for `Relevance to My Work`.

### Step 2 — extract first-N pages

```bash
cd paperhub_utils
uv run python -c "
from pathlib import Path
from pypdf import PdfReader
from paperhub.config import METADATA_ONLY_PAGE_LIMIT

pdf_path = Path('../to_be_organized/paper.pdf')
reader = PdfReader(str(pdf_path))
limit = min(METADATA_ONLY_PAGE_LIMIT, len(reader.pages))
parts = []
for index in range(limit):
    text = reader.pages[index].extract_text() or ''
    parts.append(f'--- PAGE {index + 1} ---\n{text}')
Path('/tmp/paperhub_agent_pages.txt').write_text('\n\n'.join(parts), encoding='utf-8')
print(f'Wrote first {limit}/{len(reader.pages)} pages to /tmp/paperhub_agent_pages.txt')
"
```

Read `/tmp/paperhub_agent_pages.txt`. Draft metadata from that text only — never infer from the filename.

### Step 3 — write files directly

Choose the `paper_label` using the current rule from `paperhub_utils/prompts/shared/paper_label.txt`.

```bash
LABEL="<your paper_label>"
mkdir -p "../organized/${LABEL}"
mv "../to_be_organized/paper.pdf" "../organized/${LABEL}/"
```

Then `Write` `organized/{LABEL}/{LABEL}.md` with:

```markdown
---
title: "[Full Paper Title]"
authors:
  - [Author 1]
  - [Author 2]
year: [Year]
journal: "[Journal Name or 'Unpublished manuscript']"
link: [DOI or URL if found, empty otherwise]
status:
  - initiated
tags:
  - [3-5 lowercase tags, no spaces, prefer canonical registry tags]
created: <today YYYY-MM-DD>
interest: none
contributions:
---

# [Full Paper Title]

## Abstract
[Verbatim if present in extracted pages, else "[Abstract not found in provided pages]"]

## Key Takeaways for My Research

**Main Contribution:**
[1-2 factual sentences from extracted pages.]

**Methodology/Technique:**
[1 sentence if visible, else "[To be filled]".]

**Relevance to My Work:**
[Only if MY_RESEARCH_INTERESTS gives a strong match, else "[To be filled]".]

## Quick Reference
[1 sentence.]

## Related Papers
[To be added]
```

Rules:
- `contributions:` present and empty.
- Tags lowercase with underscores; check the canonical tag registry hint via the prompt prep step in mode 2 below if you want suggestions.
- Do **not** create `ai_summary.md`.
- Do **not** invent missing metadata.

### Step 4 — shared post-AI flow

Follow `shared/post_ai.md`: validate folder, validate moved PDF, validate metadata file, run the post-summary tag flow once after the batch, commit/report. `ai_summary.md` is expected to be absent.

---

## Mode 2: full (expensive — gate first)

Run the pre-flight `AskUserQuestion` gate above. If the user picks Proceed:

### Step 1 — prepare prompt

```bash
cd paperhub_utils
uv run python -m scripts.paper_summarizer --prepare-cli-input \
  --pdf-path-arg "../to_be_organized/paper.pdf" \
  --summary-mode full \
  [--instruction "..."] \
  > /tmp/paperhub_agent_input.json
```

The JSON gives you:
- `prompt_path` — the assembled prompt (research interests + tag context + style + headings)
- `pdf_for_ai_path` — absolute path to the PDF to read
- `original_pdf_path` — same absolute path; needed for the move at the end
- `cleanup_dir` — temp dir to delete at the end

Read the prompt file with the `Read` tool.

### Step 2 — read PDF natively

Use the `Read` tool on `pdf_for_ai_path`. Claude Code reads PDFs natively (image + text). Do **not** call `pypdf` here — full mode wants the whole paper.

### Step 3 — generate content in this turn

Generate a response that follows the prompt's required structure exactly. The prompt asks for three top-level sections:

```markdown
# paper_label
<single label, lowercase, no spaces>

# metadata
---
title: "..."
authors:
  - ...
year: ...
journal: "..."
link: ...
status:
  - initiated
tags:
  - ...
created: <today>
interest: none
contributions:
---

# <Full Paper Title>

## Abstract
<verbatim from PDF>

## Key Takeaways for My Research
<...>

## Quick Reference
<...>

## Related Papers
<...>

# ai_summary
<detailed summary, ~800–1200 words, LaTeX math allowed>
```

Required: `contributions:` empty, `## Abstract` verbatim from PDF when present, tags lowercase no-spaces.

### Step 4 — write files directly

Extract the `paper_label` from your own response (the text right after `# paper_label`). Then:

```bash
LABEL="<paper_label from response>"
ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agent_input.json'))['original_pdf_path'])")
mkdir -p "organized/${LABEL}"
mv "${ORIGINAL_PDF}" "organized/${LABEL}/"
```

`Write` `organized/{LABEL}/{LABEL}.md` with everything between `# metadata` and `# ai_summary` — strip the `# metadata` heading itself, keep the YAML frontmatter and the body sections.

`Write` `organized/{LABEL}/ai_summary.md` with this frontmatter on top of the `# ai_summary` body:

```yaml
---
model: current-coding-agent
pdf_engine: coding-agent
tokens_prompt: N/A
tokens_completion: N/A
total_tokens: N/A
cost: N/A
generated: <today YYYY-MM-DD HH:MM:SS>
---
```

Then strip the `# ai_summary` heading line from the body before writing.

### Step 5 — cleanup + post-AI flow

```bash
cd paperhub_utils
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_agent_input.json'))['cleanup_dir'])")
uv run python -m scripts.paper_summarizer --cleanup-cli-input "${CLEANUP_DIR}"
```

Then `shared/post_ai.md` for validation + tag handoff + commit. The `ai_summary.md` check now applies (full mode requires it).

---

## Mode 3: enrich (expensive — gate first)

Run the pre-flight `AskUserQuestion` gate. Also run the **existing-summary `AskUserQuestion` flow** from `modes/enrich.md` (Polish past / Overwrite from scratch / Meta-fill only / Skip) before processing each folder that already has `ai_summary.md`.

`--use-past-summary` and `--instruction` work the same as for OpenRouter / Agy CLI — pass them through to `--prepare-cli-input`.

### Step 1 — prepare prompt

```bash
cd paperhub_utils
uv run python -m scripts.enrich --engine coding-agent --prepare-cli-input --folder ACF2015 \
  [--instruction "..."] \
  [--use-past-summary] \
  [--no-summary] \
  > /tmp/paperhub_enrich_input.json
```

The JSON gives you:
- `prompt_path` — assembled enrich prompt (embeds existing meta verbatim, lists missing keys, optionally embeds past summary)
- `pdf_for_ai_path` — absolute path to the folder's PDF
- `folder` — absolute path to the folder
- `paper_label` — folder name (don't change it)
- `missing_keys`, `emit_abstract`, `past_summary_used` — for reporting
- `cleanup_dir` — temp dir to delete at the end

Read the prompt file with `Read`.

### Step 2 — read PDF natively

`Read` the PDF at `pdf_for_ai_path`.

### Step 3 — generate response

The enrich prompt asks for two level-1 headings (or one when `--no-summary`):

```markdown
# metadata_patch
---
<only the keys listed in missing_keys>
---
## Abstract
<emitted only when emit_abstract=true>

# ai_summary
<detailed summary, polish-from-past when past_summary_used=true>
```

Important:
- Only fill the keys named in `missing_keys` — never `contributions` / `status` / `interest`, never overwrite a non-blank field.
- Omit the `## Abstract` block when `emit_abstract=false`.
- Skip the `# ai_summary` block when `--no-summary` was passed.

Save the response:

```bash
RESPONSE_FILE="/tmp/paperhub_agent_response_${LABEL}.txt"
# Write your generated response to ${RESPONSE_FILE}
```

### Step 4 — apply via script (NOT direct file ops)

The merge logic (only-blank-key patching, abstract section replacement, frontmatter preservation) lives in `scripts.enrich` and is fragile to reimplement. Hand the response back:

```bash
cd paperhub_utils
uv run python -m scripts.enrich --engine coding-agent --from-response --folder ACF2015 \
  --response-file "${RESPONSE_FILE}" \
  --model-label "current-coding-agent" \
  [--no-summary]
```

The `current-coding-agent` model label triggers `pdf_engine: coding-agent` in the resulting `ai_summary.md` frontmatter and skips external-CLI artifact validation. Token args are optional — leave them off; the frontmatter records `N/A`.

### Step 5 — cleanup + post-AI flow

```bash
CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('/tmp/paperhub_enrich_input.json'))['cleanup_dir'])")
uv run python -m scripts.enrich --cleanup-cli-input "${CLEANUP_DIR}"
```

Then `shared/post_ai.md` (tag handoff + commit). Commit message: `feat(papers): enrich {folder}` (or `enrich {N} folders`).

---

## Batch processing

Process papers **sequentially** in all three modes — one PDF read per turn. After every 3 papers in `full` or `enrich`, ask the user (via `AskUserQuestion`) whether to keep going.

Run the post-summary tag flow **once** after the whole batch, not per paper.

## Reporting

Same as the other engines (`modes/full.md`, `modes/metadata_only.md`, `modes/enrich.md`), with these substitutions:

- `Model used:` → `current-coding-agent`
- `Token usage:` → `N/A (read in current Claude Code session)`
- `Cost:` → `N/A`
- For `full` / `enrich`, mention pages-read implicitly ("entire PDF") rather than page counts.
