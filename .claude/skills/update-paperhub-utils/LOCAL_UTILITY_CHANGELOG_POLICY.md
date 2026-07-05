# Local Utility Changelog Policy

This policy is for maintaining this source PaperHub vault before deciding
whether to sync framework changes to the public template. Routine
`paper-summarizer`, `paper-finder`, and adopted-copy updater runs can ignore it.

Update `paperhub_utils/utility_changelog.json` when a change affects adopted
users' skills, modes, commands, prompt defaults, config shape, onboarding, tag
behavior, updater behavior, dependencies, supported model routes, or a direct
user-facing use case.

Keep release data as one JSON object with versions as keys under `entries`. Use
`YYYY.MM.DD.N` so multiple same-day releases can be ordered. Each entry should
include `update_kind` (`content`, `structural`, or `structural + content`) and a
short `how_to_apply` note.

Use `content` for plain text, skill wording, prompt-default, or context updates
that do not require migration. Use `structural` when files move, config shape
changes, commands change, update boundaries change, or users may need migration
guidance.

Add migration notes for renamed files, moved folders, changed config keys, or
changed defaults. Do not add entries for typo-only docs edits, formatting,
tests-only changes, internal refactors with no user-visible effect, private
paper-library content, or immature experimental workflows.

If an update agent cannot safely decide a prompt merge or structural migration,
it should use the available ask-user question/input tool before applying the
change.

Before syncing to the public template, check whether
`paperhub_utils/utility_changelog.json` and
`paperhub_utils/utility_manifest.json` need updates.
