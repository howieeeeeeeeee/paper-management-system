# Paper Organizer

Use `paper-organizer` to turn local PDFs or public paper links into PaperHub folders.

## Metadata-Only Batch

Use this when importing many papers and you want a fast searchable library before long summaries.

```text
\paper-organizer: metadata-only batch for everything in `to_be_organized/` using (Agy CLI / Codex CLI / OpenRouter API).
```

Output: one folder per paper under `organized/`, with the original PDF and a metadata note.

## Full Summary Pipeline

Use this when you want metadata plus `ai_summary.md` in one pass.

```text
\paper-organizer: organize new PDFs in `to_be_organized/` with full summaries using (Agy CLI / Codex CLI / OpenRouter API).
```

Add citation context when the PDF is an earlier working-paper version or has ambiguous metadata:

```text
\paper-organizer: organize `to_be_organized/xxx.pdf` with full summary using (Agy CLI / Codex CLI / OpenRouter API).
Extra: citation is Acemoglu, Daron, and Pascual Restrepo. 2020.
"Robots and Jobs: Evidence from US Labor Markets." Journal of Political Economy.
```

## Enrich Existing Paper

Use `enrich` when the metadata note already exists but `ai_summary.md` is missing or needs to be refreshed.

```text
\paper-organizer: enrich folder `organized/melitz2003trade` - refresh summary.
```

```text
\paper-organizer: enrich folder `organized/melitz2003trade` - refresh summary.
Extra: focus on the model setup, equilibrium definition, and firm heterogeneity mechanism.
```

## Metadata Fix With Extra Context

```text
\paper-organizer: metadata-only for `to_be_organized/paper.pdf`.
Extra: published in American Economic Review, 2024; PDF is an earlier working paper.
```

## Link Metadata

Paste a public paper URL directly:

```text
\paper-organizer: add https://example.org/paper as link metadata using OpenRouter.
```

Link metadata writes the normal YAML citation/workflow fields and a verbatim
public abstract. It does not write interpretive sections or `ai_summary.md`.
External engines receive prepared text only and do not browse.

## Links From Markdown

Save URLs in any Markdown or plain-text file. `papers to find.md` is a convenient
inbox:

```text
\paper-organizer: import all links under "Paper Organizer Integration Tests"
from `to_be_organized/papers to find.md` using Agy CLI.
```

The optional heading limits extraction to that section. URLs are deduplicated in
document order.

After sequential preprocessing and any coding-agent metadata additions, pure
links run through the selected external engine in parallel (four workers by
default, configurable from 1-8). Responses are written to `organized/`
sequentially and reported in the original URL order.

## Public PDFs

When a link exposes a PDF without authentication or cookies, PaperHub downloads
it to a temporary folder and routes it into a PDF batch instead of the pure-link
engine batch. Metadata-only sends the configured first pages; full mode sends
the complete public PDF. If no mode was specified, PaperHub asks once and applies
the choice to all discovered PDFs. Verified citation context is saved beside the
PDF and overrides generated bibliographic fields.

## Mixed Batches and Failures

PaperHub splits a mixed URL list into pure links, metadata-only public PDFs, and
full-summary public PDFs. Each group uses one engine and mode and runs up to the
selected worker limit. It does not overwrite an existing canonical DOI/landing
link. All scheduled jobs finish after an individual failure; successful outputs
remain, failed diagnostics are retained, and the final report restores original
URL order.
