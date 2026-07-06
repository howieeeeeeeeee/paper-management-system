# Paper Summarizer

Use `paper-summarizer` to turn PDFs into PaperHub folders with metadata notes and optional `ai_summary.md`.

## Metadata-Only Batch

Use this when importing many papers and you want a fast searchable library before long summaries.

```text
\paper-summarizer: metadata-only batch for everything in `to_be_organized/` using (AGY CLI / Codex CLI / OpenRouter API).
```

Output: one folder per paper under `organized/`, with the original PDF and a metadata note.

## Full Summary Pipeline

Use this when you want metadata plus `ai_summary.md` in one pass.

```text
\paper-summarizer: organize new PDFs in `to_be_organized/` with full summaries using (AGY CLI / Codex CLI / OpenRouter API).
```

Add citation context when the PDF is an earlier working-paper version or has ambiguous metadata:

```text
\paper-summarizer: organize `to_be_organized/xxx.pdf` with full summary using (AGY CLI / Codex CLI / OpenRouter API).
Extra: citation is Acemoglu, Daron, and Pascual Restrepo. 2020.
"Robots and Jobs: Evidence from US Labor Markets." Journal of Political Economy.
```

## Enrich Existing Paper

Use `enrich` when the metadata note already exists but `ai_summary.md` is missing or needs to be refreshed.

```text
\paper-summarizer: enrich folder `organized/melitz2003trade` - refresh summary.
```

```text
\paper-summarizer: enrich folder `organized/melitz2003trade` - refresh summary.
Extra: focus on the model setup, equilibrium definition, and firm heterogeneity mechanism.
```

## Metadata Fix With Extra Context

```text
\paper-summarizer: metadata-only for `to_be_organized/paper.pdf`.
Extra: published in American Economic Review, 2024; PDF is an earlier working paper.
```
