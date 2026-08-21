# Mode: Full

Full PDF → AI generates `{paper_label}.md` (metadata) + `ai_summary.md` (detailed summary).

Triggered by: "with summary" / "full summary" / "AI summary", or as the user's choice when asked. This is the default for direct `scripts.paper_organizer` calls (`--summary-mode full`).

Engines that support `full`: **OpenRouter** (`engines/openrouter.md`), **Agy CLI** (`engines/agy_cli.md`), **Codex CLI** (`engines/codex_cli.md`), **Coding Agent** (`engines/coding_agent.md` — **high quota**, gated by `AskUserQuestion` and a 3-paper soft batch cap).

For Agy CLI, follow `engines/agy_cli.md` with `--summary-mode full`; the prepared JSON and `--from-response` command preserve the normal full-mode output contract.

For Codex CLI, follow `engines/codex_cli.md` with `--summary-mode full`; the prepared JSON and `--from-response` command preserve the normal full-mode output contract.

## Folder structure produced

```
{paper_label}/                    # e.g., melitz2003trade/
├── {original_pdf_name}.pdf       # original paper, filename preserved
├── {paper_label}.md              # AI-generated metadata
└── ai_summary.md                 # AI-generated detailed summary
```

The metadata note ends with `[[ai_summary|Link to AI Summary]]`. The summary
starts its visible content with `[[{paper_label}|Back to Metadata]]`, after YAML
frontmatter when present. These links are added deterministically after the AI
output is written, regardless of engine.

## Validation (after the AI returns)

Save tokens — use shell tests, not full file reads.

```bash
[ -d "{output_dir}" ]                              && echo "OK" || echo "FAIL"   # 1. dir exists
[ -f "{pdf_path}" ]                                && echo "OK" || echo "FAIL"   # 2. PDF moved
[ -f "{output_dir}/{paper_label}.md" ]             && echo "OK" || echo "FAIL"   # 3. metadata
[ -f "{output_dir}/ai_summary.md" ]                && echo "OK" || echo "FAIL"   # 4. summary (REQUIRED in full mode)
```

Plus: artifact scan + YAML schema check — see `shared/post_ai.md`.

## Completion report (single paper)

```
Paper organized successfully!

Location: organized/melitz2003trade/
Files created:
   - melitz2003trade.md (AI-generated metadata)
   - ai_summary.md (AI-generated summary)
   - citation.csl.json (resolved citation sidecar)
   - melitz_2003.pdf (original paper)
Versioned: committed "feat(papers): add melitz2003trade" to backup repo (pushed)
Model used: <model name>
Token usage: X prompt + Y completion = Z total
Citation: resolved
Tag updates: 2 new (international_trade [field], heterogeneous_firms [topic]); 1 merged (melitz_model -> melitz_framework)
Related papers: 1 corrected (LP2003 -> LevinsohnPetrin2003Production); 1 ambiguous preserved; 2 without a local candidate
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
Summary (3/3 succeeded):
| Paper           | Prompt | Completion | Total  | Cost   |
|-----------------|--------|------------|--------|--------|
| melitz2003trade | 48,000 | 8,000      | 56,000 | $0.23  |
...
Versioned: committed "feat(papers): add 3 papers" to backup repo (pushed)
Citations: 3 resolved, 0 skipped, 0 failed

Tag updates this batch:
  - 4 new tags added: international_trade (field), heterogeneous_firms (topic), structural (methodology), econ559 (meta)
  - 2 tags merged into existing: melitz_model -> melitz_framework, info_asym -> information_asymmetry
  - 0 tags reused without change: 11 of 17 tags this batch were already in the registry

Related-paper reconciliation this batch:
  - 2 targets corrected: melitz2003trade: LP2003 -> LevinsohnPetrin2003Production; ACF2015: ackerbergetal2015 -> AckerbergCavesFrazer2015
  - 1 ambiguous candidate preserved: melitz2003trade: heisssetal2016inattention (2 local matches)
  - 7 references without a local candidate
```

Always include token usage when available. For Agy CLI and the standard Codex CLI flow, `cost: N/A` and token counts are unavailable.
