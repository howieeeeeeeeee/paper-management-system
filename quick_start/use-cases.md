# Use Cases

Run these prompts from the repository root. Use `to_be_organized/` for new PDFs and `organized/<folder>/` for existing paper folders.

## Skill Quick Starts

- [paper-summarizer](paper-summarizer.md): organize PDFs, create metadata notes, add or refresh `ai_summary.md`.
- [paper-finder](paper-finder.md): retrieve an existing paper from a vague memory, claim, author, tag, or snippet.
- [ask-knowledge-base](ask-knowledge-base.md): answer questions across visible Markdown notes in the Obsidian vault, with an opt-in mode for skipping generated paper metadata/summaries.
- [update-paperhub-utils](update-paperhub-utils.md): refresh skills and utility code while preserving local papers and config.

## Common Prompts

```text
\paper-summarizer: metadata-only batch for everything in `to_be_organized/` using (AGY CLI / Codex CLI / OpenRouter API).
```

```text
\paper-finder: which paper was it where dictators avoided knowing the recipient's payoff?
```

```text
\ask-knowledge-base: what do my notes say about strategic ignorance and moral wiggle room?
```

```text
\ask-knowledge-base: search my notes about confirmation bias and large language models, without papers.
```

```text
\update-paperhub-utils: check for updates and apply safe utility updates.
```

## Customizing Outputs

- Metadata fields: edit [metadata_template.txt](../paperhub_utils/prompts/shared/metadata_template.txt).
- Full summary structure: edit [summary_full.txt](../paperhub_utils/prompts/aspect/summary_full.txt).
- Shared style: edit [style.txt](../paperhub_utils/prompts/shared/style.txt).
- Tag rules: edit [tags_guidelines.txt](../paperhub_utils/prompts/shared/tags_guidelines.txt).
