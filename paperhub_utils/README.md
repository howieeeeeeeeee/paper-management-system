# paperhub_utils

This folder contains the scripts, prompts, and config used by PaperHub skills. Most users only need the files below.

## Folder Layout

- `scripts/`: command entrypoints and shell helpers. These are update-managed utility files and can normally be replaced from upstream.
- `paperhub/`: importable Python utility package used by the scripts. This is also update-managed utility code, even though it is not inside `scripts/`.
- `prompts/`: default prompt fragments. The updater compares these and asks for merge help when a user customized them.
- `config/`: local preferences, secrets, onboarding state, and template defaults. Preserve user-owned files here during updates.
- `output/`: generated reports, backups, and raw model outputs. Do not sync or replace this folder.
- `tests/`: update-managed checks for the utility code.

## Search Helpers

- `scripts/paper_search.py`: searches all visible Markdown inside each valid paper folder under `organized/`, aggregates evidence by paper label, and returns bounded context for `paper-finder`.
- `scripts/knowledge_base_search.py`: searches visible Markdown notes in the configured Obsidian vault for `ask-knowledge-base`; pass `--ignore-papers` to skip standard PaperHub metadata notes and generated paper summaries.

## Update Boundary

PaperHub treats this folder as two kinds of content:

- Update-managed utilities: `scripts/`, `paperhub/`, tests, `utility_changelog.json`, and `utility_manifest.json`.
- Merge-aware defaults: `prompts/`.
- User-owned local state: `config/.env`, `config/config.json`, `config/onboarding.json`, `config/utility_state.json`, `output/`, and any prompt customization that the updater flags for merge.

Run `update-paperhub-utils` from the repository root to refresh the update-managed parts. Prompt files are compared before update; customized prompts are merged by the agent instead of overwritten.

## Organizer Entry Points

- `scripts/paper_organizer.py`: canonical PDF/link organizer; preserves the
  legacy PDF CLI.
- `scripts/paper_link_context.py`: resolves public paper links into bounded,
  offline `source_context.txt` files and classifies pure links versus public
  PDFs for pending, metadata-only, or full routing.
- `scripts/paper_summarizer.py`: compatibility implementation for older
  commands.

Pass repeated `--link-context` values to `scripts.paper_organizer` with
`--engine openrouter|agy-cli|codex-cli` and `--max-workers 1-8` for managed
parallel pure-link generation. Public PDFs are returned as routed results and
processed separately in same-mode PDF batches.

## Prompt Files

PDF modes (`full`, `metadata-only`, `enrich`) compose their prompt from the
shared fragments below. Link metadata uses a dedicated offline fragment.

- `prompts/shared/style.txt`: shared writing style rules.
- `prompts/shared/paper_label.txt`: `# paper_label` section rules.
- `prompts/shared/metadata_template.txt`: metadata note shape and YAML fields.
- `prompts/shared/tags_guidelines.txt`: tag selection rules.
- `prompts/aspect/summary_full.txt`: full `ai_summary.md` structure (used by `full` and `enrich`).
- `prompts/aspect/enrich_intro.txt`: enrich-mode instructions.
- `prompts/aspect/past_summary.txt`: how an existing summary is reused during enrich.
- `prompts/aspect/link_metadata.txt`: YAML + abstract-only output from prepared
  public link context; external engines must not browse.
- `paperhub/prompt/builder.py`: composes the fragments per mode.

## Config Files

- `config/.env.example`: copy to `config/.env`, then add local API keys. Do not commit `config/.env`.
- `config/config.json`: runtime options, including verified available engines, git commits, metadata-only page limit, Agy CLI model defaults, Codex CLI model/reasoning/yolo defaults, and tag prompt limits.
- `paperhub/config.py`: model allowlist, script constants, and fallback research-interest text.
- `config/default_tags.yaml`: first-run canonical tag seed list.
- `utility_changelog.json`: user-facing update notes for skills and utilities.
- `utility_manifest.json`: update-managed and protected path policy used by `update_utils.py`.

After changing a template, test on one PDF or one existing folder before running a large batch.

`utility_changelog.json` stores release entries by version. The updater reads
only entries newer than the local installed version and no newer than the
upstream manifest version, so agents do not need to load the entire changelog
into context.
