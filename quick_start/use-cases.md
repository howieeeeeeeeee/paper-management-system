# Use Cases

Run these prompts from the repository root. Use `to_be_organized/` for new PDFs or link-inbox notes and `organized/<folder>/` for existing paper folders.

## Skill Quick Starts

- [paper-organizer](skills/paper-organizer.md): organize PDFs or public paper links, create metadata notes, and add or refresh `ai_summary.md` when a PDF is available.
- [paper-finder](skills/paper-finder.md): retrieve an existing paper from a vague memory, claim, author, tag, or snippet.
- [ask-knowledge-base](skills/ask-knowledge-base.md): answer questions across visible Markdown notes in the Obsidian vault, with an opt-in mode for skipping generated paper metadata/summaries.
- [update-paperhub-utils](skills/update-paperhub-utils.md): refresh skills and utility code while preserving local papers and config.

## Common Prompts

```text
\paper-organizer: metadata-only batch for everything in `to_be_organized/` using (Agy CLI / Codex CLI / OpenRouter API).
```

```text
\paper-organizer: import links under "Paper Organizer Integration Tests" from `to_be_organized/papers to find.md` using OpenRouter.
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
