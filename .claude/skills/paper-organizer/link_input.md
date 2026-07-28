# Workflow: Link Input

Use this workflow when the user provides one or more paper URLs directly or
points to a Markdown/plain-text file containing URLs.

## Contract

- The invoking coding agent owns all web access.
- External engines receive prepared text only and must not browse.
- Public metadata is limited to citation facts, abstract, and (when freely
  retrievable without authentication or cookies) an optional PDF.
- Link metadata writes the normal YAML fields, title heading, and `## Abstract`
  only. It never writes `ai_summary.md`.

## 1. Prepare Context

Run from `paperhub_utils/`:

```bash
uv run python -m scripts.paper_link_context \
  --url "https://example.org/paper" \
  --requested-mode auto
```

For a Markdown section:

```bash
uv run python -m scripts.paper_link_context \
  --link-file "../to_be_organized/papers to find.md" \
  --heading "Paper Organizer Integration Tests" \
  --requested-mode auto
```

Read each result's `context_path`. If `missing_fields` is non-empty and the
current coding-agent surface has a public web-reading tool, inspect the input or
canonical URL and append only verified facts plus source URLs under
`## Coding-Agent Additions`. Never use authenticated access or bypass a paywall.
If facts remain unavailable, keep the placeholders.

Replace the placeholder with a fenced JSON object so the organizer can treat
the additions as authoritative over engine output:

```json
{
  "canonical_url": "https://doi.org/10.1234/example",
  "metadata": {
    "title": "Verified title",
    "authors": ["Verified Author"],
    "year": 2026,
    "journal": "Verified Journal",
    "doi": "10.1234/example",
    "abstract": "Verbatim public abstract"
  },
  "source_urls": ["https://public.example/citation"]
}
```

Omit unavailable values. An intentional coding-agent addition overrides weak
landing-page values such as a download filename.

Use `--requested-mode metadata-only|full` when the user already chose a PDF
mode. Otherwise use `auto`. After preprocessing, route by the returned value:

| Route | Action |
|---|---|
| `link-metadata` | Add the context to the pure-link parallel batch. |
| `pdf-pending-mode` | Ask once: metadata-only or full; apply that choice to all pending PDFs. |
| `pdf-metadata` | Add the public PDF to the metadata-only PDF batch. |
| `pdf-full` | Add the public PDF to the full-summary PDF batch. |

## 2. Run the Managed Pure-Link Batch

Pass all completed contexts together. The command processes pure links in
parallel, skips duplicate/existing canonical links before engine calls, and
returns public PDFs as routed results with a structured citation sidecar:

```bash
uv run python -m scripts.paper_organizer \
  --link-context "CONTEXT_1" \
  --link-context "CONTEXT_2" \
  --engine openrouter \
  --max-workers 4 \
  --pdf-mode metadata-only
```

Use `--engine agy-cli` or `--engine codex-cli` for those external engines.
Omit `--pdf-mode` when no pending PDFs exist. The managed pool allows `1-8`
workers, lets all scheduled calls finish after a failure, finalizes successful
responses sequentially, and retains only failed CLI diagnostics.

OpenRouter receives plain text without `tools` or `plugins`. Managed Agy uses a
per-run `--model` plus isolated stdout/stderr/log files. Managed Codex is
ephemeral and read-only with `web_search="disabled"`. None receives a PDF or a
URL outside the prepared context.

## 3. Process Routed PDF Groups

Read `pdf_path`, `citation_sidecar_path`, and `summary_mode` from routed results.
Run one PDF batch per mode using the same selected engine and worker limit:

- `metadata-only`: the existing PDF workflow sends only the configured first
  pages.
- `full`: the existing PDF workflow sends the complete publicly downloaded PDF.

The generated sidecar travels with the PDF, enters the prompt as authoritative
citation context, and deterministically overrides generated title, authors,
year, journal, canonical link, and abstract. For OpenRouter, pass every PDF path
for one mode to one `scripts.paper_organizer` call with `--summary-mode` and
`--max-workers`. For Agy or Codex, follow the engine playbook: prepare each PDF,
run at most the selected worker count concurrently with isolated files, and
apply responses sequentially.

## 4. Low-Level Single-Link Compatibility

OpenRouter single-context calls remain valid:

```bash
uv run python -m scripts.paper_organizer \
  --link-context "CONTEXT_PATH"
```

This is a plain text OpenRouter request. The payload must not contain `tools`,
`plugins`, or an online model suffix.

For manual Agy or Codex calls, allocate a fresh artifact directory first — the
same stale-response hazard as the PDF path applies here, so never reuse fixed
`/tmp` names (see the Run Integrity section in `engines/agy_cli.md` and
`engines/codex_cli.md`). Then prepare one offline prompt:

```bash
WORK=$(mktemp -d)
uv run python -m scripts.paper_organizer \
  --prepare-link-input \
  --external-cli-engine agy-cli \
  --link-context "CONTEXT_PATH" > "$WORK/input.json"
```

Read `prompt_path`, then call Agy with the returned model via per-run `--model`,
without a URL or file attachment. Use the same offline wrapper and sentinels as
the managed path. Save stdout, stderr, and log, then apply it with:

```bash
uv run python -m scripts.paper_organizer \
  --from-link-response \
  --external-cli-engine agy-cli \
  --link-context "CONTEXT_PATH" \
  --response-file "$WORK/output.txt" \
  --agy-stderr-file "$WORK/stderr.txt" \
  --agy-log-file "$WORK/agy.log" \
  --model-label "MODEL_LABEL"

rm -rf "$WORK"
```

Prepare the prompt with `--external-cli-engine codex-cli`, then call `codex exec`
with the configured model/reasoning pair and `-c 'web_search="disabled"'`. Do
not provide the URL separately. Apply the response with
`--from-link-response --external-cli-engine codex-cli` and the prepared context.

## 5. Current Coding Agent

Use the same prepared prompt and context. The agent may have browsed while
preparing `Coding-Agent Additions`, but generation itself must use only the
saved context. Apply with `--from-link-response --external-cli-engine coding-agent`.

## 6. Validate and Clean Up

- Metadata YAML includes title, authors, year, journal, link, status, tags,
  created, interest, importance, and empty contributions.
- The body contains only the title heading and `## Abstract`.
- `ai_summary.md` and interpretive sections are absent.
- Pure-link folders contain no PDF. Public PDFs must be processed only in their
  routed PDF group and must match the downloaded `public_pdf_path`.
- Use the exact `output_dir` returned by the command; never infer it.
- Reassemble the final report in original context order across all three groups.
- Delete the context `cleanup_dir` after success or abandonment. Retain it while
  diagnosing a failure.

During disposable integration tests, skip the tag handoff and all post-run
versioning. Remove only the exact test-created output folder after validation.
