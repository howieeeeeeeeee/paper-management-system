# Use Cases

Run these prompts from the repository root. Use `to_be_organized/` for new PDFs or link-inbox notes and `organized/<folder>/` for existing paper folders.

## Skill Quick Starts

- [Import an existing project literature collection](import-project-literature.md): turn a paper folder or BibTeX file into a tagged, citation-ready PaperHub batch, then keep its bibliography current.
- [paper-organizer](skills/paper-organizer.md): organize PDFs or public paper links, create metadata notes, and add or refresh `ai_summary.md` when a PDF is available.
- [paper-finder](skills/paper-finder.md): retrieve an existing paper from a vague memory, claim, author, tag, or snippet.
- [citation-resolver](skills/citation-resolver.md): audit citation coverage and explicitly create or repair per-paper citation records.
- [bibliography-builder](skills/bibliography-builder.md): export selected papers to BibTeX or a formatted Markdown reference list.
- [ask-knowledge-base](skills/ask-knowledge-base.md): answer questions across visible Markdown notes in the Obsidian vault, with an opt-in mode for skipping generated paper metadata/summaries.
- [paperhub-obsidian](obsidian/paperhub-obsidian.md): create or edit Obsidian Markdown, Bases, Canvas maps, and optional live-vault workflows.
- [update-paperhub-utils](skills/update-paperhub-utils.md): refresh skills and utility code while preserving local papers and config.

## Common Prompts

```text
/paper-organizer : metadata-only batch for everything in `to_be_organized/` using (Agy CLI / Codex CLI / OpenRouter API).
```

```text
/paper-organizer : import links under "Paper Organizer Integration Tests" from `to_be_organized/papers to find.md` using OpenRouter.
```

```text
/paper-finder : which paper was it where dictators avoided knowing the recipient's payoff?
```

```text
/citation-resolver : audit citation coverage for papers tagged experiments.
```

```text
/bibliography-builder : build references.bib from papers tagged experiments.
```

```text
/ask-knowledge-base : what do my notes say about strategic ignorance and moral wiggle room?
```

```text
/ask-knowledge-base : search my notes about confirmation bias and large language models, without papers.
```

```text
/paperhub-obsidian : create a Canvas literature map linking my notes on Bayesian persuasion.
```

```text
/update-paperhub-utils : check for updates and apply safe utility updates.
```

## Customizing Outputs

- Metadata fields: edit [metadata_template.txt](../paperhub_utils/prompts/shared/metadata_template.txt).
- Full summary structure: edit [summary_full.txt](../paperhub_utils/prompts/aspect/summary_full.txt).
- Shared style: edit [style.txt](../paperhub_utils/prompts/shared/style.txt).
- Tag rules: edit [tags_guidelines.txt](../paperhub_utils/prompts/shared/tags_guidelines.txt).
