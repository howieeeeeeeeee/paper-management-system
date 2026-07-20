# Upstream Refresh (maintainer-only)

Use this playbook only when the user explicitly asks to check or refresh the
bundled source snapshot from `https://github.com/kepano/obsidian-skills`.

The refresh script refuses to run unless the private vault's maintainer-only
`public-template-sync` skill is present. In a public adopter copy, stop and tell
the user to run `update-paperhub-utils` instead.

## Check first

From the PaperHub root, run:

```bash
python3 .claude/skills/paperhub-obsidian/scripts/sync_upstream.py --check
```

Read the JSON report and summarize:

- the installed and candidate full commit SHAs;
- added, modified, and removed mirrored files;
- local drift, if any;
- added, removed, or renamed top-level upstream skills; and
- changes that introduce commands, dependency installation, networking, or new
  executable resources.

The check is read-only. If fetching fails, report the failure and leave the
current mirror untouched.

## Apply a reviewed update

For content changes within the existing skill set:

```bash
python3 .claude/skills/paperhub-obsidian/scripts/sync_upstream.py --apply
```

If the report marks the update as structural, explain the added/removed skill
set and obtain explicit user approval. Then run:

```bash
python3 .claude/skills/paperhub-obsidian/scripts/sync_upstream.py --apply --allow-structural
```

Never bypass a local-drift error. Compare the drift with `upstream-lock.json`
and ask whether the local edits should be preserved elsewhere or discarded
before retrying.

The script may replace only `skills/`, `LICENSE`, and `upstream-lock.json` inside
this skill. It must never edit `SKILL.md`, `UPSTREAM.md`, `scripts/`, `agents/`,
PaperHub configuration, papers, tags, or user notes.

## Post-apply review

1. If the top-level upstream skill set changed, update the route table and
   safeguards in `SKILL.md` before continuing.
2. Confirm the mirrored files and `LICENSE` match the commit recorded in
   `upstream-lock.json`.
3. Run the skill validator on this router and every nested upstream skill.
4. Run the focused upstream-sync tests, then the full PaperHub test suite.
5. If shipped behavior changed, update `utility_changelog.json` and bump
   `utility_manifest.json` according to the local changelog policy. Use
   `content` for wording-only changes and `structural + content` when the skill
   set, commands, dependencies, or update boundaries changed.
6. Run `versioning-with-git` to back up the private vault framework changes.
7. Ask separately before running `public-template-sync`; an upstream refresh
   never publishes automatically.
