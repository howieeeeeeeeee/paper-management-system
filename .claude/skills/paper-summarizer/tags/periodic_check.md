# Tag System: Periodic Check

This doc covers the user-triggered periodic cleanup flow for the tag system.

Use this only when the user says "do a periodic tag check" / "audit tags" / "tag system check" / "clean up tags".

For the normal batch-level flow after summarizing or enriching papers, read `tags/post_summary_update.md` instead.

The periodic flow is token-light by design: use scan outputs and compact registry files; never read the full `tags_summary.md` table just for a similarity check.

## Registry layout

Lives in `tags/` under the paper-library root:

```
tags/
├── tags_summary.md          ← THE user-facing file (consolidated table, hand-editable)
└── _internal/
    ├── registry.json        ← machine-readable mirror, regenerated
    ├── field_names.txt      ← one tag per line (cheap lookup for similarity check)
    ├── topic_names.txt
    ├── methodology_names.txt
    ├── meta_names.txt
    ├── round1_merges.json   ← archived round-1 normalization mapping
    └── CHANGELOG.md         ← append-only normalization history
```

`tags_summary.md` has one consolidated table: `| tag | type | count | notes |`. Sorted by (type-order, -count). To reclassify a tag, the user edits the `type` column directly; the next `bootstrap_registry` run re-sorts the table while preserving the edit.

## Scripts

All scripts are under `paperhub_utils/`. Run with `uv run python -m paperhub.tag_utils.<name>` from that directory.

**Periodic-only scripts (in `tag_utils.periodic.<name>`):**

| Script | What it does |
|---|---|
| `tag_utils.periodic.scan_tags` | Walks `organized/`, returns `{tag: {count, papers}}` JSON. Read-only. |
| `tag_utils.periodic.bootstrap_registry` | Regenerates `tags_summary.md` and all `_internal/` files from a scan JSON. Idempotent. Preserves user-edited types/notes by reading existing `tags_summary.md` first. |
| `tag_utils.periodic.apply_renames` | Surgical line-edits to `tags:` blocks across all metadata files. Requires `--merges-file PATH` (JSON `{old: new}`). `--dry-run` / `--apply`. |
| `tag_utils.periodic.normalize_fields` | Standardizes `interest:` (scalar) and `status:` (list) frontmatter. `--dry-run` / `--apply`. |

---

## Periodic Check Flow

Trigger phrases: "do a periodic tag check", "audit the tag system", "tag system check", "clean up the tags".

This is a heavier flow that surfaces accumulated drift since the last check.

### Steps

1. **Scan and summarize.**

   ```bash
   cd paperhub_utils
   uv run python -m paperhub.tag_utils.periodic.scan_tags --pretty --out /tmp/tags_now.json
   ```

2. **Look for drift.** Pull tags with `count == 1` introduced since last check, plus the full top-N of each type. Skim for:
   - **Casing variants:** `AI` / `ai`, `LLM` / `llm` (always merge to lowercase)
   - **Hyphen vs underscore:** `machine-learning` vs `machine_learning` (merge to underscore)
   - **Singular vs plural:** `network` vs `networks`, `merger` vs `mergers` (judgment call)
   - **Abbreviation vs full form:** `VC` vs `venture_capital`, `IV` vs `instrumental_variables`
   - **Typos:** `microthoery` → `micro_theory`
   - **Promotion candidates:** if a `topic` tag now has count ≥ 5 and looks field-level, nudge user to retype it (just edit the `type` column in `tags_summary.md`)

3. **Build proposal.** Show the user a markdown table of proposed merges: `| Canonical | Variants → merged in | Combined count | Type | Rationale | Decision |`. Wait for user to approve, flip canonical, or skip.

4. **Apply.** Encode the merges in a temp JSON file:

   ```bash
   cat > /tmp/round_N_merges.json <<'EOF'
   {"old1": "new1", "old2": "new2"}
   EOF

   uv run python -m paperhub.tag_utils.periodic.apply_renames --dry-run --merges-file /tmp/round_N_merges.json
   # Review diff
   uv run python -m paperhub.tag_utils.periodic.apply_renames --apply  --merges-file /tmp/round_N_merges.json
   ```

   If `interest:`/`status:` field drift has crept back in:

   ```bash
   uv run python -m paperhub.tag_utils.periodic.normalize_fields --dry-run
   uv run python -m paperhub.tag_utils.periodic.normalize_fields --apply
   ```

5. **Regenerate registry.**

   ```bash
   uv run python -m paperhub.tag_utils.periodic.scan_tags --pretty --out /tmp/tags_now.json
   uv run python -m paperhub.tag_utils.periodic.bootstrap_registry \
       --scan /tmp/tags_now.json --tags-dir ../tags
   ```

6. **Append to `tags/_internal/CHANGELOG.md`.** New section `## Round N — YYYY-MM-DD` with the merges, counts before/after, and reproduce commands.

7. **Archive the merges file** for reproducibility:
   ```bash
   cp /tmp/round_N_merges.json ../tags/_internal/round_N_merges.json
   ```

8. **Commit.**

   ```bash
   git add tags/ organized/
   git commit -m "chore(tags): periodic tag normalization (round N)"
   ```

9. **Report.** Show the user: "Round N done. Was X tags, now Y. Top merges: `old → new` (N papers). Anything else to clean?"

### Reviewing tag types after periodic check

If you want the user to review specific `?`-flagged or low-confidence tags (e.g., new tags that defaulted to `topic`), open `tags_summary.md` and ask which rows they'd like to retype. They can either edit the `type` column directly or tell you and you'll edit it. Re-run `bootstrap_registry` to re-sort.

---

## What this skill does NOT do here

- Does not auto-run the periodic check on a schedule. User triggers it explicitly.
- Does not modify the prompt fragments under `prompts/shared/` and `prompts/aspect/` — that's Phase 2 of the broader plan.
- Does not delete tags with count 0 — flag them in the report, leave the row in place.
- Does not split `tags_summary.md` into per-type files — by design, one consolidated table is the user surface.
