---
name: update-paperhub-utils
description: Update PaperHub skills and utility files from the public template while preserving user config, papers, tags, and prompt customizations. Triggers when users ask to update, refresh, pull latest PaperHub utilities, sync skills/utils, or see what is new in PaperHub utilities.
---

# Update PaperHub Utilities

The project's root folder contains a `.claude` directory. Open
`.claude/skills/update-paperhub-utils/SKILL.md` from that root for the
canonical workflow and rules.

In brief: run `cd paperhub_utils && uv run python -m scripts.update_utils --check`, read the report's
`changelog_entries` slice for update kind and "How to apply" advice, apply safe
framework updates, semantically merge any customized prompt files, record the
installed version, run tests, and report what changed. Never overwrite user
papers, runtime config, tags, API keys, Obsidian state, or local prompt
customizations. Treat `paperhub_utils/scripts/**` and
`paperhub_utils/paperhub/**` as update-managed utility code that can normally be
replaced from upstream. If a merge or structural migration choice is unclear,
ask the user before applying it.
