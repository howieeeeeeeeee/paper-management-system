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
| 7 | Reciprocal navigation (when `ai_summary.md` exists) | metadata ends with `[[ai_summary\|Link to AI Summary]]`; summary's first visible line is `[[{paper_label}\|Back to Metadata]]` |

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

## 3. Optional citation resolution

Read `CITATION_RESOLVE_AFTER_ORGANIZE` from `paperhub.config`. When it is false,
skip this section completely so the default organizer behavior is unchanged.

When it is true, run this hook once for each newly organized metadata-only,
full, or link-metadata paper after validation/auto-fix and before tag updates.
Do not run it for `enrich`.

- Existing usable metadata link: run deterministic resolution once.
- Blank link with the current coding agent: when
  `CITATION_CURRENT_AGENT_SEARCH_MISSING_LINK` is true, search once by title,
  author, and year, then pass one candidate through the resolver's identity
  validation.
- Blank link with OpenRouter, Agy CLI, or Codex CLI processing: skip; external
  paper-processing engines never browse or search for a link.
- Blank link with search disabled: skip.

Use the canonical resolver in best-effort mode:

```bash
cd paperhub_utils
uv run python -m scripts.citation_resolver resolve \
  --label "{paper_label}" \
  --best-effort \
  [--candidate-links-file /tmp/paperhub_candidate_link.json]
```

This hook is optional and gets one attempt only. Never retry, switch models,
enter the failed-paper recovery flow, roll back a valid paper, or block tags and
versioning because citation resolution failed. When enabled, retain one compact
completion line such as `Citation: resolved`, `Citation: skipped — no link
available`, or `Citation: failed — identity mismatch`.

## 4. Tag flow handoff

After auto-fix, ALWAYS run the post-summary tag flow once for the batch (see `tags/post_summary_update.md`). Capture: count of new tags added (with type), count of merges, count of tags reused unchanged.

## 5. Version (git commit via the backup repo)

The vault has **no** `.git` (it lives in an iCloud folder). Do not run `git` inside the vault.
Instead, run the **`versioning-with-git` skill** — it mirrors the vault into the out-of-iCloud
git backup folder, commits **all** changes there (papers + tags + any config/prompt edits from
this run, in one commit), and pushes if the user syncs to a remote. Read
`.claude/skills/versioning-with-git/SKILL.md` and follow it, passing the commit message:

- Single paper: `feat(papers): add {paper_label}`
- `enrich` mode: `feat(papers): enrich {paper_label}` (or `enrich {N} folders`)
- Multiple papers: `feat(papers): add {label1}, {label2}, ...`
- Many papers — multi-line body:

  ```text
  feat(papers): add {N} papers

  - {label1}
  - {label2}
  ...
  ```

The versioning skill already checks `USE_GIT`, `SYNC_TO_REMOTE_GIT`, and `GIT_BACKUP_ABS_PATH`
and skips cleanly when versioning is off or the backup folder is unset.

**Skip this step if:** the user explicitly said no commit. (Everything else — `USE_GIT` false,
no backup path, git unavailable — the versioning skill handles and reports.)

## 6. Report

Use the per-mode completion-report template in `modes/{mode}.md`. Always include:

- Token usage when available (Agy CLI and the standard Codex CLI flow: token counts unavailable, `cost: N/A`; Coding Agent: no token info).
- **Tag updates line/section** — count + list of newly added tags (with type), count + list of merges (`new_variant -> existing_canonical`), count of tags reused unchanged. If nothing changed: `Tag updates: all N tags reused from registry, no changes.`

## 7. Handle partial failures

For batches, check the script's `failed` count. If > 0, surface to the user via `AskUserQuestion`:

- Header: "Failed papers"
- Question: "{N} paper(s) failed. What would you like to do?"
- Options: `Abandon`, `Retry`, `Try a different model`

If "Try a different model" → second AskUserQuestion with options from the active engine's allowlist (`MODEL_LIST`, `AGY_CLI_MODEL_LIST`, or `CODEX_CLI_MODEL_REASONING_PAIRS` for Codex CLI).

**Never auto-retry with a different model. Never present a model not in the active engine's allowlist.**
