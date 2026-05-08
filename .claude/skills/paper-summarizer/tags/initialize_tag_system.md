# Tag System: Initialize

Read this during onboarding when `onboard.md` reaches the tag step, or any time the user asks to "process tag additions" / "pick up new tags." This flow seeds the canonical tag registry from a default seed pack and processes user-supplied additions from `tags/tag_initialization.md`.

**Do not interrogate the user about their domain, fields, methodologies, topics, or meta tags.** The seed is the default; the additions file is opt-in and user-driven.

## Inputs

- `paperhub_utils/seeds/default_tags.yaml` — curated seed pack (ships with the repo)
- `tags/tag_initialization.md` — the user's additions file (also ships with the repo as a template; the user edits it)
- Starter tag notes from the user's onboarding request, if any
- Current files under `tags/`, if they already exist

## Routing

| Situation | Run sections |
| --- | --- |
| No `tags/_internal/registry.json` exists | §1 (seed) → §2 (additions template) → §3 (process additions if `status: ready`) → §5 (finish) |
| Registry exists | §4 (validate) → §3 (process additions if `status: ready`) → §5 (finish) |

## 1. Seed the registry from the default pack

1. Read `paperhub_utils/seeds/default_tags.yaml`. Parse the four type lists (`field`, `methodology`, `topic`, `meta`).
2. Normalize each tag: trim whitespace, lowercase, replace spaces with underscores, dedupe within type. Preserve established acronyms only when intentional (e.g., keep `IO` capitalized if it appears that way in the seed).
3. Write the canonical artifacts:
   - `tags/_internal/registry.json` — every seed tag at `count: 0`
   - `tags/_internal/field_names.txt`, `topic_names.txt`, `methodology_names.txt`, `meta_names.txt` — one tag per line per type
   - `tags/_internal/CHANGELOG.md` — first entry: `<YYYY-MM-DD> seed registered: <profile> profile (<N> tags total)`
   - `tags/tags_summary.md` — consolidated table

Minimal `registry.json` shape:

```json
{
  "scanned": 0,
  "total_tags": <N>,
  "by_type": {
    "field": [{"tag": "applied_micro", "count": 0, "notes": ""}],
    "topic": [],
    "methodology": [],
    "meta": []
  }
}
```

`tags_summary.md` shape:

```markdown
# Tags Summary

**N canonical tags**, 0 occurrences across 0 papers.

## All tags

| tag | type | count | notes |
|---|---|---:|---|
| `applied_micro` | field | 0 |  |
| `market_design` | field | 0 |  |
```

Set `total_tags` to the count of seed tags across all four types.

## 2. Ensure the additions template is in place

1. If `tags/tag_initialization.md` already exists, leave its body alone.
2. If it does not exist, generate it with the template body shown below.
3. If the user's onboarding request mentioned starter tag notes (e.g., "add tags `behavioral_io`, course `ec301`"), pre-fill them into the right `## type` sections AND set the frontmatter to `status: ready` so §3 picks them up in the same onboarding pass. Otherwise leave the type sections empty (or with the inline `#` example comments) and the frontmatter at `status: not_ready`.

Template body (used only when generating inline — keep in sync with `tag_init/tag_initialization.md` in the repo):

```markdown
---
status: not_ready
---

# Tag additions

The default seed pack registered a starter set of common tags at count 0.
This file is for adding tags **specific to you**: your courses, advisor's
seminar, niche subfields, project labels.

## How to use

1. Add tags under the right `## type` heading below, one per line.
2. Lowercase + underscores work best (the agent normalizes anyway).
3. Lines starting with `#` and blank lines are ignored.
4. When you're done editing, change `status: not_ready` to `status: ready`.
5. Tell the agent to "process tag additions" — or it picks this up on the
   next onboarding pass.

## field

## methodology

## topic

## meta

---

## Applied additions
```

## 3. Process the additions file (only if status: ready)

1. Read `tags/tag_initialization.md`. Parse the YAML frontmatter.
2. If `status` is anything other than `ready`, skip this section silently. Do not nag.
3. For each `## type` section:
   - Split into lines.
   - Drop blank lines and lines starting with `#`.
   - Normalize each entry: trim, lowercase, replace spaces with underscores.
   - Dedupe within the section.
4. For each normalized addition:
   - If the tag already exists in the registry under **any** type, skip and note it for the report.
   - Otherwise, append it to the registry at `count: 0` under the type given in the file.
5. Update the canonical artifacts: `registry.json`, the four `*_names.txt` files, and `tags_summary.md`.
6. Append to `tags/_internal/CHANGELOG.md`:

   ```text
   <YYYY-MM-DD> user additions registered: <N> tags from tag_initialization.md (<K> already existed, skipped)
   ```

7. Rewrite `tags/tag_initialization.md`:
   - Flip frontmatter to `status: applied`.
   - Clear the four `## type` sections — keep the headings, remove all body content (including any inline `#` comments the user added or kept).
   - Append a dated entry under `## Applied additions`:

     ```markdown
     ### YYYY-MM-DD
     - field: behavioral_io
     - meta: ec301
     - skipped (already exists): theory
     ```

   Do not delete prior `## Applied additions` entries — they are the audit trail.

## 4. Existing-registry validation

When `tags/_internal/registry.json` already exists:

1. Validate that `registry.json` parses and has `by_type.field`, `by_type.topic`, `by_type.methodology`, and `by_type.meta`.
2. If any of the four name files (`field_names.txt`, etc.) is missing or out of sync with the registry, regenerate that name file from the registry.
3. Do **not** reseed. The user has already started using the system.
4. Do not overwrite existing tag counts or notes.
5. Still proceed to §3 to process any pending additions.

## 5. Finish

1. Re-read `tags/_internal/registry.json` and confirm it parses.
2. Confirm the four type name files exist and align with the registry.
3. Report:
   - counts by type
   - any additions processed in §3 (or "none — left at status: not_ready" / "skipped — file does not exist")
4. Update the `initialize_tag_system` step in `paperhub_utils/misc/onboarding.json` to `done`.
5. Return to `onboard.md`.

## Notes

- For seed tags and additions-file tags, edit `registry.json`, `tags_summary.md`, the relevant name file, and `CHANGELOG.md` directly. Do **not** use `tag_utils.register_tag --add` for these — that helper records `count: 1` for post-paper registrations.
- The post-summary tag flow (`tags/post_summary_update.md`) is separate and runs after each paper batch — that is where `count` actually increments above 0.
- The legacy interactive tag-init flow (asking the user about domain/fields/etc.) has been retired. If the user explicitly says "I want to interview through tags," fall back to a single `AskUserQuestion` asking which seed profile to load (currently only `economics-phd` ships) and otherwise still drop the additions file for them to fill at their own pace.
