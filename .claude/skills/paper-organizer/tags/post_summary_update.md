# Tag System: Post-Organization Update

Run this flow **once after all paper-summary threads finish**. Multi-threaded OpenRouter batches may summarize in parallel; tag work is serial, post-batch.

This is the batch-level tag flow used by `shared/post_ai.md`. Do not read `tags/periodic_check.md` for normal summarize/enrich batches.

## Inputs

- The list of `paper_label` values that were just summarized
- The current registry state in `tags/_internal/registry.json`

## Registry layout

Lives in `tags/` under the paper-library root:

```
tags/
├── tags_summary.md          ← user-facing consolidated table
└── _internal/
    ├── registry.json        ← machine-readable mirror, regenerated
    ├── field_names.txt      ← one tag per line
    ├── topic_names.txt
    ├── methodology_names.txt
    ├── meta_names.txt
    └── CHANGELOG.md
```

`tags_summary.md` has one consolidated table: `| tag | type | count | notes |`. Sorted by (type-order, -count). To reclassify a tag, the user edits the `type` column directly; the next `bootstrap_registry` run re-sorts the table while preserving the edit.

## Scripts

Run all scripts from `paperhub_utils/`:

| Script | What it does |
|---|---|
| `tag_utils.register_tag --suggest-merge TAG --type T` | Reads the canonical registry through the safe loader, scores similarity across all types, prints small JSON: `{new_tag, guessed_type, similar: [{tag, existing_type, score}, ...]}`. Empty `similar` list = no near-match. |
| `tag_utils.register_tag --add TAG --type T [--from-paper LABEL]` | Appends a brand-new tag to `tags_summary.md` and `_internal/`. |
| `tag_utils.register_tag --rename OLD NEW --paper LABEL` | Rewrites the `tags:` block in one paper's metadata after a user accepts a merge. |

## Steps

1. **Classify just-summarized papers' tags.**

   ```bash
   cd paperhub_utils
   uv run python -m paperhub.tag_utils.classify_batch_tags --pretty "$LABEL_1" "$LABEL_2" ...
   ```

   The output includes:
   - `papers`: tags by paper label
   - `reused`: unique batch tags already present in the canonical registry
   - `candidates`: unique batch tags that need add/merge handling
   - `registry_source`: usually `tags/_internal/registry.json`; if the JSON
     file was missing, malformed, or empty, the script falls back to
     `tags/tags_summary.md` instead of silently classifying every tag as new

2. **Repair a stale machine mirror when the classifier had to fall back.**
   If `registry_source` ends with `tags_summary.md` or `registry_warnings` is
   non-empty, rebuild the machine files before continuing:

   ```bash
   cd paperhub_utils
   uv run python -m paperhub.tag_utils.periodic.scan_tags --pretty --out /tmp/tags_now.json
   uv run python -m paperhub.tag_utils.periodic.bootstrap_registry \
       --scan /tmp/tags_now.json \
       --tags-dir ../tags
   ```

3. **Use the classifier output for the diff.** Tags in `candidates` are the
   only tags that need add/merge handling. Tags in `reused` count as **reused
   unchanged** unless later renamed by a merge decision.

4. **For each candidate new tag**, in stable order:

   **a. Type it.** Decide the type using these heuristics:
   - Course/conference codes (`econ\d+`, `\d{4}_*`, `LEMA`, `PSUAI`) → `meta`
   - Subdiscipline names (`labor_economics`, `behavioral_economics`, `IO`, `macroecon`, ...) → `field`
   - Methods (`empirical`, `experimental`, `structural`, `machine_learning`, `econometrics`, ...) → `methodology`
   - Otherwise → `topic`

   If genuinely uncertain, ask the user with the 4 type options.

   **b. Ask the script for similar existing tags.** Do not read any names file yourself.

   ```bash
   uv run python -m paperhub.tag_utils.register_tag --suggest-merge NEW_TAG --type TYPE
   ```

   The script prints small JSON to stdout, e.g.:

   ```json
   {"new_tag": "info_asym", "guessed_type": "topic",
    "similar": [{"tag": "information_asymmetry", "existing_type": "topic", "score": 0.9}]}
   ```

   `similar: []` means no near-match. Otherwise the array has up to 3 candidates.

   **c. Decide replace vs add.**

   - **`similar` is empty:** add the new tag.

     ```bash
     uv run python -m paperhub.tag_utils.register_tag \
         --add NEW_TAG --type TYPE --from-paper LABEL
     ```

   - **`similar` has candidates:** ask the user. Show the top candidate(s) with existing type. If the candidate's `existing_type` differs from your `guessed_type`, mention that.

     > New tag `<new>` (paper `<label>`) looks similar to existing `<existing>` (type: `<existing_type>`, score 0.9). Replace, or keep as a new tag?
     >
     > Options: **Replace** / **Keep as new**

     - **Replace:**

       ```bash
       uv run python -m paperhub.tag_utils.register_tag \
           --rename NEW_TAG EXISTING_TAG --paper LABEL
       ```

     - **Keep as new:**

       ```bash
       uv run python -m paperhub.tag_utils.register_tag \
           --add NEW_TAG --type TYPE --from-paper LABEL
       ```

5. **Refresh registry counts** after add/rename decisions:

   ```bash
   uv run python -m paperhub.tag_utils.periodic.scan_tags --pretty --out /tmp/tags_now.json
   uv run python -m paperhub.tag_utils.periodic.bootstrap_registry \
       --scan /tmp/tags_now.json \
       --tags-dir ../tags
   ```

   The bootstrap preserves user-edited types/notes by parsing the existing `tags_summary.md` data table first.

6. **Capture tag-update counts** for the completion report and commit body:

   - New tags added: count + list with type, e.g. `labor_supply (field)`
   - Merges: count + list, e.g. `info_asym -> information_asymmetry`
   - Tags reused unchanged: count of tags from the just-summarized papers that required no add/rename

   If nothing changed, report: `Tag updates: all N tags reused from registry, no changes.`

7. **Tags land in the same commit as the papers.** Do not commit here. The single commit for
   the batch is made by the **`versioning-with-git`** step in `shared/post_ai.md` §6, whose
   `git add -A` captures `tags/` and `organized/` together in the out-of-iCloud backup repo. Pass
   the tag-update counts into that commit body if you like:

   ```text
   feat(papers): add <labels>

   Tag updates:
   - new: tag1 (field), tag2 (topic)
   - merged: old_tag -> existing_tag
   - reused unchanged: N
   ```

## Token discipline

- Use `tag_utils.classify_batch_tags` once to determine new vs reused tags.
- Do not read `tags_summary.md` manually for similarity checks; the safe loader uses it only as an automatic fallback when `registry.json` is invalid.
- Do not read `_internal/*_names.txt` manually for similarity checks; `register_tag --suggest-merge` returns compact JSON.
