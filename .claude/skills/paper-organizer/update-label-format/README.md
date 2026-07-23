# Update an existing paper-label format

This optional toolkit is for a reviewed, one-time migration of an existing
PaperHub library. It is intentionally not part of the paper-organizer router:
changing hundreds of folder names and vault links should happen only when a
user asks for it explicitly.

The workflow separates editorial judgment from filesystem changes:

1. Agree on a naming rule with examples for one, two, and three-or-more authors.
2. Inventory the current library and split the mapping work into stable batches.
3. Have mapping agents propose labels from metadata without changing any files.
4. Have one root agent review every proposal and all bibliographic collisions.
5. Build a frozen manifest and preflight the entire configured Obsidian vault.
6. Apply through temporary names, atomically rewrite exact references, and
   verify or roll back.
7. Keep the temporary manifest, review, verification, and preimage files until
   the user explicitly approves cleanup.

Start by copying and filling the task in
[handoff_instruction.md](handoff_instruction.md). Mapping agents should receive
the bounded instructions in [MAPPING_AGENT_PROMPT.md](MAPPING_AGENT_PROMPT.md),
plus exactly one batch input and output path.

## Commands

Run from `paperhub_utils/`. Choose a temporary work directory for this
migration; reuse the same value for every command.

```bash
MIGRATION_WORK="../.paperhub_tmp/update_label_format"

uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" inventory

uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" make-batches --batch-count 10 --apply
```

After the mapping agents create every `batch_XX.output.jsonl`, preview and then
write the consolidated artifacts:

```bash
uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" merge

uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" merge --apply
```

The root agent must read `review.md`, resolve every collision or uncertain row,
and rerun `merge --apply` after any mapping correction. Then run the read-only
application preflight:

```bash
uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" apply
```

Only this command changes the library and configured vault:

```bash
uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" apply --apply
```

Refresh verification without changing vault content:

```bash
uv run python ../.claude/skills/paper-organizer/update-label-format/label_migration.py \
  --work-dir "$MIGRATION_WORK" verify --apply
```

## Mapping output

Each output row copies its input row and fills:

- `action`: `rename` or `preserve`;
- `proposed_label`: the final label, or the unchanged old label when preserving;
- `confidence`: `high`, `medium`, or `low`;
- `notes`: a concise reason for any metadata correction or inferred word break;
- `review_flags`: a JSON list of anything the root agent must inspect.

The script validates coverage, safe ASCII labels, exact casing, target
uniqueness, frozen source hashes, and vault-wide reference counts. It never
decides whether a topic phrase is editorially good and never merges or deletes
papers.

## Safety boundaries

- Treat duplicate-looking records as a bibliographic question. Compare title,
  authors, year, DOI/URL, abstract, created date, and local PDF hashes.
- For true duplicate copies, keep both folders. Give the earliest-created copy
  the base label and later copies a deterministic timestamp suffix.
- For distinct papers that would collide, add discriminating title/topic words
  before considering a suffix.
- Back up every text file that will change. The script stores preimages under
  the chosen work directory.
- Scan the configured Obsidian vault, not only PaperHub. External writes may
  require sandbox approval.
- Exclude `.obsidian`, trash, caches, virtual environments, Git internals, and
  migration artifacts.
- Never remove the temporary work directory until the user explicitly confirms
  that everything passes.
