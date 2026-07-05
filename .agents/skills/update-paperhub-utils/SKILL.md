---
name: update-paperhub-utils
description: Update PaperHub skills and utility files from the public template while preserving user config, papers, tags, and prompt customizations. Triggers when users ask to update, refresh, pull latest PaperHub utilities, sync skills/utils, or see what is new in PaperHub utilities.
---

# Update PaperHub Utilities

Use this skill to update an adopted PaperHub copy from the public template repo:

```text
https://github.com/howieeeeeeeeee/paper-management-system
```

Use the best available model for this task. The updater is partly deterministic,
but prompt conflicts require semantic merge judgment.

## Critical Rules

- Never overwrite user-owned content: `organized/`, `to_be_organized/`,
  `tags/_internal/`, `.env`, Obsidian workspace files, local output folders, or
  runtime/onboarding config.
- Prompt files are merge targets, not simple overwrite targets.
- `paperhub_utils/scripts/**` and `paperhub_utils/paperhub/**` are
  update-managed utility code. In normal updates, let the helper replace them;
  review only when it reports local edits or a structural conflict.
- If the helper reports `needs_agent_merge`, read the local prompt and upstream
  prompt, then merge intent manually before recording the update.
- Preserve prompt headings and response contracts expected by scripts.
- Do not promote immature downloader/fetcher/browser workflows in the changelog.
- If a merge, migration, or structural decision is difficult to decide, use the
  available ask-user tool (`AskUserQuestion`, `ask_user_input`, or equivalent)
  before applying it.

## 0. Self-update this skill first (before Step 1)

**The very first action is to update this `update-paperhub-utils` skill itself from
upstream, then re-read it, and only then proceed.** The update logic in these
instructions changes over time; running the newest version of the updater's own steps
avoids applying stale or unsafe update behavior.

1. Fetch the upstream template and overwrite only this skill's files:

   ```bash
   TMP=$(mktemp -d)
   git clone --depth 1 https://github.com/howieeeeeeeeee/paper-management-system.git "$TMP/upstream" \
     && cp "$TMP/upstream/.claude/skills/update-paperhub-utils/SKILL.md" \
           .claude/skills/update-paperhub-utils/SKILL.md \
     && cp "$TMP/upstream/.agents/skills/update-paperhub-utils/SKILL.md" \
           .agents/skills/update-paperhub-utils/SKILL.md 2>/dev/null
   rm -rf "$TMP"
   ```

   If the clone fails (e.g. offline), note it and continue with the current skill version.

2. **Re-read the refreshed `.claude/skills/update-paperhub-utils/SKILL.md` and follow the
   newest instructions from the top.** Bootstrap once per run: if the refresh changed the
   file, adopt the new steps; if it made no change, you are already current. Then continue
   to the workflow below.

## Workflow

1. From the repository root, check what is available:

   ```bash
   cd paperhub_utils
   uv run python -m scripts.update_utils --check
   ```

2. Read the generated report under `paperhub_utils/output/update_reports/`.
   Summarize:
   - available version,
   - `changelog_entries` from the report, not the full changelog file,
   - update kind (`content`, `structural`, or mixed),
   - short "how to apply" advice from the changelog,
   - safe file updates,
   - files needing agent merge or review.

3. Apply safe updates:

   ```bash
   cd paperhub_utils
   uv run python -m scripts.update_utils --apply
   ```

4. For every `needs_agent_merge` prompt:
   - compare the local file, backup file, and upstream file from the report,
   - preserve local user customizations,
   - incorporate upstream improvements,
   - remove duplicate or contradictory rules,
   - keep required headings and output contracts.
   - ask the user when the intended behavior is unclear.

   For structural updates, compare the previous local structure with the new
   upstream structure and follow the changelog's "How to apply" advice. If the
   structure affects user-owned config or local workflow choices, ask before
   moving, deleting, or rewriting anything.

5. After manual merges, record the current managed files as the installed
   utility version:

   ```bash
   cd paperhub_utils
   uv run python -m scripts.update_utils --record-current
   ```

6. Run focused checks:

   ```bash
   cd paperhub_utils
   uv run python -m unittest discover -s tests
   ```

7. Report the result with:
   - installed version,
   - applied files,
   - merged prompts,
   - skipped files,
   - any follow-up action the user should take.

## Prompt Merge Standard

A prompt merge is successful only if it preserves the user's local behavioral
preference and still includes upstream safety/format requirements. If those
conflict, ask the user which behavior should win instead of guessing.
