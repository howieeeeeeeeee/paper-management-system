# Mode: Metadata-Only

First N pages of PDF → AI generates `{paper_label}.md` only. No `ai_summary.md`.

Triggered by: "metadata only" / "no summary" / "without summary", or as the user's choice when asked. CLI flag: `--summary-mode metadata-only`.

The page limit is `metadata_only_page_limit` in `paperhub_utils/config/config.json`, exported to scripts as `METADATA_ONLY_PAGE_LIMIT` in `paperhub_utils/paperhub/config.py`.

Engines that support `metadata-only`: **OpenRouter** (`engines/openrouter.md`), **Agy CLI** (`engines/agy_cli.md`), **Codex CLI** (`engines/codex_cli.md`), **Coding Agent** (`engines/coding_agent.md` — cheapest mode for this engine; reads only the first `METADATA_ONLY_PAGE_LIMIT` pages, no quota gate).

For Agy CLI, follow `engines/agy_cli.md` with `--summary-mode metadata-only`; the prepare step sends only the first configured pages to Agy and `--from-response` still moves the original PDF.

For Codex CLI, follow `engines/codex_cli.md` with `--summary-mode metadata-only`; the prepare step sends only the first configured pages to Codex and `--from-response` still moves the original PDF.

## Folder structure produced

```
{paper_label}/                    # e.g., melitz2003trade/
├── {original_pdf_name}.pdf       # original paper, filename preserved
└── {paper_label}.md              # AI-generated metadata
```

No `ai_summary.md`. Absence is expected.

## Validation (after the AI returns)

```bash
[ -d "{output_dir}" ]                              && echo "OK" || echo "FAIL"   # 1. dir exists
[ -f "{pdf_path}" ]                                && echo "OK" || echo "FAIL"   # 2. PDF moved
[ -f "{output_dir}/{paper_label}.md" ]             && echo "OK" || echo "FAIL"   # 3. metadata
# 4. SKIP the ai_summary.md check — it's expected to be absent.
```

Plus: artifact scan + YAML schema check — see `shared/post_ai.md`.

## Completion report (single paper)

```
Paper organized successfully (metadata-only)!

Location: organized/melitz2003trade/
Files created:
   - melitz2003trade.md (AI-generated metadata)
   - citation.csl.json (resolved citation sidecar)
   - melitz_2003.pdf (original paper)
Versioned: committed "feat(papers): add melitz2003trade" to backup repo (pushed)
Model used: <model name>
Pages sent: 3 of 42
Token usage: X prompt + Y completion = Z total
Citation: resolved
Tag updates: 2 new (international_trade [field], heterogeneous_firms [topic])
Related papers: 1 corrected (LP2003 -> LevinsohnPetrin2003Production); 0 ambiguous; 2 without a local candidate
```

The `Citation:` line is required whenever `CITATION_RESOLVE_AFTER_ORGANIZE` is
on (see `shared/post_ai.md` §3). List `citation.csl.json` under files created
only when resolution actually wrote it.

The `Related papers:` line is always required (see `shared/post_ai.md` §5 and
§7). When the note has no exact `Related Papers` heading, write `Related papers:
not applicable — no exact Related Papers heading`; when the helper ran but
changed nothing, still report the ambiguous and no-local-candidate counts.

## Completion report (batch)

```
Summary (3/3 succeeded, metadata-only):
| Paper           | Pages | Prompt | Completion | Total  | Cost  |
|-----------------|-------|--------|------------|--------|-------|
| melitz2003trade | 3/42  | 4,500  | 1,200      | 5,700  | $0.02 |
...
Versioned: committed "feat(papers): add 3 papers" to backup repo (pushed)
Citations: 3 resolved, 0 skipped, 0 failed

Tag updates this batch:
  - 4 new tags added: ...
  - 2 tags merged into existing: ...

Related-paper reconciliation this batch:
  - 2 targets corrected: melitz2003trade: LP2003 -> LevinsohnPetrin2003Production; ACF2015: ackerbergetal2015 -> AckerbergCavesFrazer2015
  - 1 ambiguous candidate preserved: melitz2003trade: heisssetal2016inattention (2 local matches)
  - 7 references without a local candidate
```

Always include token usage when available. For Agy CLI and the standard Codex CLI flow, `cost: N/A`. For Agy CLI, Codex CLI, and Coding Agent, no token info.
