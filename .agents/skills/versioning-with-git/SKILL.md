---
name: versioning-with-git
description: Version the paper library with git WITHOUT keeping a .git inside the (iCloud-synced) vault. Copies the whole vault into a separate out-of-iCloud "git backup folder" that IS a git repo, and commits all changes there (optionally pulling/pushing a remote). Triggers when the user wants to "version / commit / back up / snapshot my library", "sync to git/GitHub", or after paper-summarizer finishes a batch and needs to commit. NOT for summarizing/organizing papers (that is paper-summarizer).
---

# Versioning with Git (out-of-vault backup)

The working paper library lives inside an iCloud-synced Obsidian vault. A live `.git`
directory inside an iCloud folder gets corrupted (iCloud and git fight over `.git/**`), so the
vault itself holds **no** `.git`. Instead, history lives in a **separate git repo outside
iCloud** — the "git backup folder". This skill copies the whole vault into that folder,
commits **all** changes there, and (optionally) pulls before / pushes after.

This is the single commit step for the whole system: `paper-summarizer`'s post-AI flow, the tag
flows, and any manual "back up my library" request all route here.

## Inputs

- **commit_message** (required): the conventional-commit message, e.g.
  `feat(papers): add melitz2003trade`, `feat(papers): add 3 papers`,
  `feat(papers): enrich {folder}`, `chore(tags): periodic tag normalization (round N)`.
- **Config** (read from `paperhub_utils/config/config.json` → `git` block):

  ```bash
  cd paperhub_utils
  uv run python -c "from paperhub.config import USE_GIT, SYNC_TO_REMOTE_GIT, GIT_BACKUP_ABS_PATH; print(USE_GIT, SYNC_TO_REMOTE_GIT, GIT_BACKUP_ABS_PATH)"
  ```

  - `USE_GIT` — master on/off switch.
  - `SYNC_TO_REMOTE_GIT` — when true, `git pull --ff-only` before and `git push` after.
  - `GIT_BACKUP_ABS_PATH` — absolute path of the out-of-vault backup repo (`SRC` is the vault
    root = `PAPERHUB_ROOT`; `DST` is this path).

## Gating (check before doing anything)

- If `USE_GIT` is false → **skip**, report `versioning skipped: use_git=false`.
- If `GIT_BACKUP_ABS_PATH` is empty/None → **skip** with a clear warning: the git backup folder
  is not set; re-run onboarding or set `git.backup_abs_path` in `config.json`. **Never** fall
  back to `git init`/commit inside the vault.
- If `GIT_BACKUP_ABS_PATH` looks like a cloud path (contains `Mobile Documents`, `Dropbox`,
  `Google Drive`, `OneDrive`) → **warn** loudly; a git repo there will corrupt. Proceed only if
  the user insists.
- If the vault contains `.icloud` placeholder files (not-yet-downloaded stubs) → **warn**: the
  vault must be fully downloaded ("Keep Downloaded") or those files back up as empty stubs. Check
  with `find "$SRC" -name '*.icloud' | head`.
- If `DST` is missing or has no `.git` → this is first-time setup; see **First-time setup**.

## Workflow

Always quote `"$SRC"` / `"$DST"` — the vault path contains spaces.

```bash
cd paperhub_utils
SRC=$(cd .. && pwd)                 # vault root (PAPERHUB_ROOT)
DST="<GIT_BACKUP_ABS_PATH>"         # from config
```

1. **Pull (only if `SYNC_TO_REMOTE_GIT`):**

   ```bash
   git -C "$DST" pull --ff-only
   ```

   If the pull is not fast-forward (diverged / conflict), **stop and report** — do not merge,
   rebase, or force. Let the user reconcile.

2. **Copy the whole vault into the backup.** The one required exclusion is the backup's own
   `.git/` — the vault has none, so without this `--delete` would wipe the backup's history.
   Everything else is copied:

   ```bash
   rsync -a --delete --exclude='.git/' "$SRC/" "$DST/"
   ```

   `git add -A` in the backup still respects the vault's `.gitignore` (copied along), so
   machine-local files (`.venv/`, `.env`, `paperhub_utils/output/`, `.DS_Store`) land in the
   working tree but are never committed.

   macOS note: accented filenames may differ in Unicode form (NFD in the vault vs NFC in a git
   checkout). The backup repo's git defaults (`core.precomposeunicode`, `core.ignorecase`)
   absorb that, so `git -C "$DST" status` shows only real edits, never a wall of accented papers.

3. **Stage and commit ALL changes** (papers, tags, config edits, prompt edits — whatever the
   workflow touched):

   ```bash
   git -C "$DST" add -A
   git -C "$DST" commit -m "{commit_message}"
   ```

   If `git -C "$DST" status --porcelain` is empty, skip the commit and report "nothing to
   commit".

4. **Push (only if `SYNC_TO_REMOTE_GIT`):**

   ```bash
   git -C "$DST" push
   ```

5. **Report:** backup path, short commit hash + message, files changed, and push status
   (pushed / local-only / skipped).

## First-time setup (backup folder missing or has no `.git`)

Use when `DST` is empty or not yet a repo:

1. `git --version` (bail with an install hint if git is unavailable).
2. Create `DST` if missing; copy the whole vault in (step 2 above).
3. Initialize and make the first commit:

   ```bash
   git -C "$DST" init -b main
   git -C "$DST" add -A
   git -C "$DST" commit -m "{commit_message}"
   ```

4. If `SYNC_TO_REMOTE_GIT`, ask the user for the remote URL and wire it up — **never invent a
   URL**:

   ```bash
   git -C "$DST" remote add origin <user-provided-url>
   git -C "$DST" push -u origin main
   ```

## Critical rules

- **Never** create or keep a `.git` inside the vault (iCloud). All history lives in `DST`.
- The backup folder MUST be a normal local folder **outside** any cloud-synced tree.
- The mirror copies the whole folder; the only exclusion is `.git/`, so the backup repo's own
  history survives every copy.
- Do not `git push` / `git pull` unless `SYNC_TO_REMOTE_GIT` is true. Local commits are the
  default.
- On a non-fast-forward pull or any push rejection, stop and surface it — never force.
- Paths with spaces: always quote `"$SRC"` / `"$DST"`; run `uv run` from `paperhub_utils/`.

## What this skill does NOT do

- Does NOT summarize, organize, or enrich papers — that is `paper-summarizer`.
- Does NOT keep any git state inside the vault.
