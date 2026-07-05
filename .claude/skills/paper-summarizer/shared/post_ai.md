# Shared post-AI steps

These steps run after the AI engine returns, regardless of which engine produced the output. Mode-specific bits (folder structure, validation #4 for `ai_summary.md`, completion report) live in `modes/{mode}.md`.

## 1. Validate output files

Token-light: use shell tests and `rg`, not full file reads.

| # | Check | Command |
|---|---|---|
| 1 | Output directory exists | `[ -d "{output_dir}" ]` |
| 2 | PDF moved into folder | `[ -f "{pdf_path}" ]` |
| 3 | Metadata file exists | `[ -f "{output_dir}/{paper_label}.md" ]` |
| 4 | (mode-specific summary check) | see `modes/{mode}.md` |
| 5 | No markup artifacts | `rg -l 'cite_start\|cite_end\|<ref>\|</ref>' "{output_dir}"` |
| 6 | Valid YAML frontmatter | parses; has `title`, `authors`, `year`, `tags`, `contributions` (empty); body has `## Abstract`; tags have no spaces |

## 2. Auto-fix issues

- **Remove artifacts**: `Edit` to strip `cite_start`, `cite_end`, `<ref>`, `</ref>` from `.md` files.
- **Tag spaces**: replace ` ` with `_` inside YAML tag list items.
- **Missing required fields**: insert placeholders:

  ```yaml
  title: "[Title needed]"
  authors:
    - "[Author needed]"
  year: 0
  tags:
    - untagged
  contributions:
  ```

- **Missing `## Abstract`**: insert

  ```markdown
  ## Abstract
  [Abstract not found in provided pages]
  ```

Always report any auto-fixes in the completion report.

## 3. Tag flow handoff

After auto-fix, ALWAYS run the post-summary tag flow once for the batch (see `tags/post_summary_update.md`). Capture: count of new tags added (with type), count of merges, count of tags reused unchanged.

## 4. Git commit

Before committing, check `USE_GIT` from the Python config. It is loaded from `paperhub_utils/config/config.json` unless `PAPERHUB_USE_GIT` overrides it:

```bash
cd paperhub_utils
uv run python -c "from paperhub.config import USE_GIT; print(USE_GIT)"
```

Single paper:

```bash
# Run from the paper-library root.
git add .
git commit -m "feat(papers): add {paper_label}"
```

For `enrich` mode use `feat(papers): enrich {paper_label}` (or `enrich {N} folders`).

Multiple papers:

```bash
git commit -m "feat(papers): add {label1}, {label2}, ..."
```

Or many:

```bash
git commit -m "feat(papers): add {N} papers

- {label1}
- {label2}
..."
```

**Skip git if:** `USE_GIT` is false, the user explicitly said no commit, output is outside the git repo, or git is unavailable.

## 5. Report

Use the per-mode completion-report template in `modes/{mode}.md`. Always include:

- Token usage when available (Agy CLI and the standard Codex CLI flow: token counts unavailable, `cost: N/A`; Coding Agent: no token info).
- **Tag updates line/section** — count + list of newly added tags (with type), count + list of merges (`new_variant -> existing_canonical`), count of tags reused unchanged. If nothing changed: `Tag updates: all N tags reused from registry, no changes.`

## 6. Handle partial failures

For batches, check the script's `failed` count. If > 0, surface to the user via `AskUserQuestion`:

- Header: "Failed papers"
- Question: "{N} paper(s) failed. What would you like to do?"
- Options: `Abandon`, `Retry`, `Try a different model`

If "Try a different model" → second AskUserQuestion with options from the active engine's allowlist (`MODEL_LIST`, `AGY_CLI_MODEL_LIST`, or `CODEX_CLI_MODEL_REASONING_PAIRS` for Codex CLI).

**Never auto-retry with a different model. Never present a model not in the active engine's allowlist.**
