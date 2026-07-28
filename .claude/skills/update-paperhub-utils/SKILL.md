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
  `tags/_internal/`, `.env`, Obsidian workspace files, local output folders,
  runtime/onboarding config, or `paperhub_utils/config/research_interests.md`.
- **Let the verdict set the amount of friction.** A `clean` copy must apply
  without a single question; only ask about files that actually diverge.
- Prompt files are merge targets, not simple overwrite targets.
- `paperhub_utils/scripts/**` and `paperhub_utils/paperhub/**` are
  update-managed utility code. In normal updates, let the helper replace them;
  review only when it reports local edits or a structural conflict.
- **Never leave a `needs_agent_merge` or `needs_review` file unresolved.** The
  helper skips them by design; if you skip them too they stay frozen and drift
  further every release. Resolve each one with the user before recording.
- Research interests live in the protected
  `paperhub_utils/config/research_interests.md`, never in `paperhub/config.py`.
  `--apply` migrates them automatically from the old inline location.
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

### 1. Check, and read the verdict first

```bash
cd paperhub_utils
uv run python -m scripts.update_utils --check
```

The plan reports a **`verdict`** summarizing how far this copy has diverged.
**Let it decide how much you ask the user.** Do not walk a user with an
untouched copy through file-by-file decisions.

| Verdict | Meaning | What to do |
|---|---|---|
| `clean` | Nothing locally modified | Apply everything. Ask nothing. |
| `prompts-only` | Only prompt files diverge | Merge those (§3); everything else applies silently. |
| `framework-modified` | Skills or utility code edited locally | Resolve each file with the user (§3). |
| `no-baseline` | No recorded install state | One bulk confirmation (§2), not one question per file. |

Read the generated report under `paperhub_utils/output/update_reports/` and
summarize: available version, `changelog_entries` **from the report** (not the
full changelog file), update kind, the changelog's "how to apply" advice, and
the counts per action.

### 2. The `no-baseline` case

Without a recorded baseline, a local edit is indistinguishable from simply
running an older release, so every differing file would otherwise fall through
to a silent replace. Ask **once**, for the whole set:

> No installed-version record was found, so I cannot tell which of these N files
> you customized. Backups are written before anything is replaced.
>
> Options: **Take upstream for all** (recommended; backups written) /
> **Review them individually** / **Cancel**

Only expand to per-file questions if the user picks review.

### 3. Apply, then resolve what needs a decision

```bash
cd paperhub_utils
uv run python -m scripts.update_utils --apply
```

`--apply` replaces safe files, writes backups, and reports
`research_interests_migration` when it rescued research interests from the old
inline location. Files marked `needs_agent_merge` or `needs_review` are **not**
applied — they are yours to resolve now. Never leave them unresolved: a skipped
file stays skipped every future release and drifts further each time.

For each such file, show the user what actually differs, then ask:

> `<path>` — you have local changes and upstream also changed this file.
>
> Options: **Take upstream** (your version is backed up at `<backup path>`) /
> **Keep mine** (this file will diverge further each release) /
> **Integrate** (I will show you the merged result before writing)

Group by file, not by hunk. If the user picks **Integrate**, show the proposed
merged content and get approval before writing it.

When merging a prompt: preserve the user's local behavioral preference, keep
upstream safety and format requirements, drop duplicated or contradictory rules,
and keep every heading and response contract the scripts expect. If the local
preference and an upstream requirement genuinely conflict, ask which wins rather
than guessing.

For structural updates, compare the previous local structure with the new
upstream structure and follow the changelog's "How to apply" advice. Ask before
moving, deleting, or rewriting anything that touches user-owned config or
workflow choices.

### 4. Record and verify

```bash
cd paperhub_utils
uv run python -m scripts.update_utils --record-current
uv run python -m pytest -q
```

Record only after every decision from §3 is resolved — `--record-current`
baselines whatever is on disk, so recording early bakes in an unresolved
conflict. If `pytest` is missing, install it once with `uv sync --extra dev`.

### 5. Report, then walk the user through what they gained

Report: installed version, applied files, merged prompts, resolved conflicts and
how each was resolved, and whether research interests were migrated.

Then give a short **walkthrough**, because a version number tells the user
nothing about what they can now do:

1. **What's new for you** — two or three lines derived from the
   `changelog_entries` actually applied, phrased as capabilities rather than
   file changes. Say "you can now find a paper from a vague memory with
   `paper-finder`", not "added paper-finder skill". Skip entries that change
   nothing the user would notice.
2. **Anything they must do** — only if a changelog entry has migration steps, or
   a conflict was resolved as "keep mine" and will keep drifting.
3. **Where to read more** — `README.md` at the project root was refreshed by
   this update; point them there for the current feature list and examples, and
   name the public template as the source of truth:
   `https://github.com/howieeeeeeeeee/paper-management-system`.

Keep it to a few lines. Do not paste the changelog, and do not promote
immature downloader/fetcher/browser workflows.

## Prompt Merge Standard

A prompt merge is successful only if it preserves the user's local behavioral
preference and still includes upstream safety/format requirements. If those
conflict, ask the user which behavior should win instead of guessing.
