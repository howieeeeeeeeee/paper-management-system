# paperhub_utils

This folder contains the scripts, prompts, and config used by the `paper-summarizer` skill. Most users only need the files below.

## Prompt Files

All three modes (`full`, `metadata-only`, `enrich`) compose their prompt from the fragments below. Edit the fragment to change behavior across modes.

- `prompt/shared/style.txt`: shared writing style rules.
- `prompt/shared/paper_label.txt`: `# paper_label` section rules.
- `prompt/shared/metadata_template.txt`: metadata note shape and YAML fields.
- `prompt/shared/tags_guidelines.txt`: tag selection rules.
- `prompt/aspect/summary_full.txt`: full `ai_summary.md` structure (used by `full` and `enrich`).
- `prompt/aspect/enrich_intro.txt`: enrich-mode instructions.
- `prompt/aspect/past_summary.txt`: how an existing summary is reused during enrich.
- `prompt/builder.py`: composes the fragments per mode.

## Config Files

- `.env.example`: copy to `.env`, then add local API keys. Do not commit `.env`.
- `misc/config.json`: runtime options, including git commits, metadata-only page limit, Agy/Gemini CLI model defaults, and tag prompt limits.
- `config.py`: model allowlist, script constants, and fallback research-interest text.
- `seeds/default_tags.yaml`: first-run canonical tag seed list.

After changing a template, test on one PDF or one existing folder before running a large batch.
