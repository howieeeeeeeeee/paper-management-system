# Use Cases

Run these prompts from the repository root. Use `to_be_organized/` for new PDFs and `organized/<folder>/` for existing paper folders.

## Initial Setup: Metadata-Only Batch

Use this when you are importing many papers for the first time and want a fast searchable library before generating long summaries.

```text
\paper-summarizer: metadata-only batch for everything in `to_be_organized/` using (AGY CLI / Codex CLI / OpenRouter API).
```

Output: one folder per paper under `organized/`, with the original PDF and a metadata note.

## Full Summary Pipeline

Use this when you want metadata plus `ai_summary.md` in one pass.

```text
\paper-summarizer: organize new PDFs in `to_be_organized/` with full summaries using (AGY CLI / Codex CLI / OpenRouter API).
```

Example with citation help for better metadata (sometime you download a WP version of a published paper, providing extra citation info will be useful):

```text
\paper-summarizer: organize `to_be_organized/xxx.pdf` with full summary using (AGY CLI / Codex CLI / OpenRouter API).
Extra: citation is Acemoglu, Daron, and Pascual Restrepo. 2020.
"Robots and Jobs: Evidence from US Labor Markets." Journal of Political Economy.
```

## Three New Papers With Full Summaries

Put three PDFs in `to_be_organized/`, then run:

```text
\paper-summarizer: organize the three PDFs in `to_be_organized/` with full summaries using (AGY CLI / Codex CLI / OpenRouter API).
```

Add context when the PDFs are working-paper versions, renamed downloads, or missing clean citation pages.

## Add AI Summary to Existing Paper

Use `enrich` when the metadata note already exists but `ai_summary.md` is missing or needs to be refreshed.

Without extra instruction:

```text
\paper-summarizer: enrich folder `organized/melitz2003trade` - refresh summary.
```

With extra instruction:

```text
\paper-summarizer: enrich folder `organized/melitz2003trade` - refresh summary.
Extra: focus on the model setup, equilibrium definition, and firm heterogeneity mechanism.
```

## Metadata Fix With Extra Context

Use this when the PDF title page is ambiguous, old, or different from the published version.

```text
\paper-summarizer: metadata-only for `to_be_organized/paper.pdf`.
Extra: published in American Economic Review, 2024; PDF is an earlier working paper.
```

## OpenRouter Model Choice

Use this when you want a specific allowed OpenRouter model.

```text
\paper-summarizer: enrich `organized/melitz2003trade` via OpenRouter with model <model-name>.
Extra: compare to Melitz (2003); keep the summary useful for exam notes.
```

## Find A Half-Remembered Paper

Use this when you know the paper is already in `organized/` but only remember a claim, mechanism, or example.

```text
\paper-finder: which paper was it where dictators avoided knowing the recipient's payoff?
```

For a deeper explanation of why each candidate matched:

```text
\paper-finder: detailed search for the moral wiggle room paper about dictators avoiding payoff information.
```

## Update Skills And Utilities

Use the best available model (SOTA GPT w/ xhigh thinking or Opus w/ xhigh thinking) because the updater may need to compare and merge customized prompt files.

```text
\update-paperhub-utils: check for updates and apply safe utility updates.
```

The update flow preserves local papers, tags, API keys, runtime config, Obsidian state, generated outputs, and customized prompts. Utility release notes live in [utility_changelog.json](../paperhub_utils/utility_changelog.json).

## Customizing Outputs

- Metadata fields: edit [metadata_template.txt](../paperhub_utils/prompts/shared/metadata_template.txt).
- Full summary structure: edit [summary_full.txt](../paperhub_utils/prompts/aspect/summary_full.txt).
- Shared style: edit [style.txt](../paperhub_utils/prompts/shared/style.txt).
- Tag rules: edit [tags_guidelines.txt](../paperhub_utils/prompts/shared/tags_guidelines.txt).
