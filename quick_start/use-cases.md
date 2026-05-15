# PaperHub prompt cookbook

Run prompts from the **PaperHub** repository root in your coding agent unless your setup notes otherwise. Paths below are relative to that root.

## Ingest and summarize

| Scenario                               | Reference             | Mode            | Prompt                                                                      |
| -------------------------------------- | --------------------- | --------------- | --------------------------------------------------------------------------- |
| New paper(s)                           | `to_be_organized/`    | `full`          | `paper-summarizer: organize new PDFs in to_be_organized/ - full summary.`   |
| Many papers, ingest first              | `to_be_organized/`    | `metadata-only` | `paper-summarizer: metadata-only batch for everything in to_be_organized/.` |
| Polish / refresh `ai_summary.md`       | `organized/<folder>/` | `enrich`        | `paper-summarizer: enrich folder <folder> - refresh summary.`               |
| Summary with chosen model (OpenRouter) | `organized/<folder>/` | `enrich`        | `paper-summarizer: enrich <folder> via OpenRouter with model <model-name>.` |

Replace `<folder>` with the paper folder name under `organized/` (the `paper_label`).

## Optional extra context

Add free text in the same prompt when it helps the model use the right citation, emphasis, or summary shape.

- `... Extra: published in American Economic Review, 2024; PDF is still a working paper.`
- `... Extra: please spell out all model setup details (timing, equilibrium notion, parameter constraints) in ai_summary.md.`
- `... Extra: compare to Melitz (2003); our goal is exam notes on heterogeneity vs selection.`
