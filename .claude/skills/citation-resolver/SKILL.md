---
name: citation-resolver
description: Audit or resolve PaperHub citation coverage for papers selected by exact labels or Boolean tag conditions. Use when the user asks which papers have citation data, how many need links, to create or repair per-paper citation.csl.json files, or to resolve missing citations. Audit requests are strictly read-only and never become apply operations automatically.
---

# Citation Resolver

Use the deterministic citation utilities under `paperhub_utils/`. One paper's
canonical citation is `organized/{PaperLabel}/citation.csl.json`; legacy
`*.citation.md` files remain separate inputs.

Treat `citation_exist: true` in the canonical metadata note as a derived confirmation that `citation.csl.json` exists and passes Citation Resolver validation. Write or repair this property only during an explicit resolve or backfill operation, including for a valid citation file that the operation skips; never write it during an audit, infer it from a metadata link alone, or set it to `false` automatically.

## Select papers

Translate natural-language conditions into exact labels and tag predicates.
Tags are case-folded exact matches, never fuzzy matches.

```bash
cd paperhub_utils
uv run python -m scripts.paper_select \
  --all-tag behavioral_economics \
  --all-tag experiments \
  --any-tag ambiguity \
  --any-tag beliefs \
  --output-manifest /tmp/paperhub_selection.json
```

Use repeated `--label` for explicit labels. The resulting manifest must contain
the explicit ordered label list used by every later command.

## Audit

For “check,” “audit,” “how many,” or coverage questions, run only:

```bash
cd paperhub_utils
uv run python -m scripts.citation_resolver audit \
  --labels-file /tmp/paperhub_selection.json \
  --report-file /tmp/paperhub_citation_audit.json
```

Audit performs no network requests and changes no files. Report mutually
exclusive counts and labels for:

- `ready`
- `needs_citation_from_link`
- `needs_link_then_citation`
- `blocked`

Also report invalid existing citation files as a diagnostic. Bound long label
lists in chat and retain the complete temporary report. End with:

> No files were changed. Ask me to proceed if you want these citations resolved.

Never continue from audit to resolution without an explicit apply request.

## Resolve

Before applying, rerun selection and audit so stale manifests are not trusted.
Existing valid citation files are skipped unless the user explicitly requests
refresh behavior.

After the resolver finishes, set `citation_exist: true` for every selected paper whose final `citation.csl.json` validates, including `resolved` and `skipped_valid` results. Preserve all other frontmatter and write metadata notes atomically.

For labels with blank links:

1. Read `CITATION_CURRENT_AGENT_SEARCH_MISSING_LINK` from `paperhub.config`.
2. If false, leave them unresolved.
3. If true, use only the current coding agent's web search to find a candidate
   from title, first author, and year. Search at most ten missing-link papers in
   one batch; resolve larger selections in explicit chunks.
4. Save candidates as a JSON object mapping labels to public URLs:

   ```json
   {"candidate_links": {"PaperLabel": "https://doi.org/10.x/example"}}
   ```

5. Pass that file to the deterministic resolver. A candidate is written only
   after title plus author/year identity validation succeeds. Never replace a
   nonblank metadata link.

### Inaccessible or metadata-poor nonblank links

If deterministic resolution fails because a nonblank link is a raw PDF, a
blocked landing page, or otherwise lacks usable citation metadata:

1. Do not retry it automatically or silently replace the link.
2. Search authoritative sources by exact title, authors, and year. Prefer a DOI;
   otherwise use the publisher, journal, repository, or working-paper landing
   page.
3. Show the user the current link, the verified replacement, and the evidence
   connecting it to the same paper. Obtain explicit approval before editing the
   nonblank `link:` value.
4. If no DOI or accessible official landing page can be verified, ask the user
   for an official citation export in `.ris` or `.bib` format. Inspect the
   export for a DOI or official URL and use its fields to confirm identity, then
   return to step 3. The resolver does not import RIS or BibTeX directly, so if
   the export contains no usable public URL, leave the paper unresolved and
   report that limitation. Do not ask for another copy of a PDF that is already
   in the paper folder.
5. After approval, replace only that paper's `link:` value, rerun the audit,
   and give the deterministic resolver one attempt. Validate paper identity and
   report the outcome.
6. Without approval, leave both metadata and citation data unchanged.

```bash
cd paperhub_utils
uv run python -m scripts.citation_resolver resolve \
  --labels-file /tmp/paperhub_selection.json \
  --candidate-links-file /tmp/paperhub_candidate_links.json \
  --best-effort \
  --report-file /tmp/paperhub_citation_result.json
```

The resolver attempts each selected paper once. It validates CSL structure,
writes atomically, preserves rich DOI CSL fields, and reports per-paper
`resolved`, `skipped_valid`, `needs_candidate_link`, `identity_mismatch`,
`blocked`, or `failed` results. Do not retry, switch models, or weaken identity
thresholds automatically.

After any files change, run `versioning-with-git` unless the user explicitly
declined a commit. Report created/repaired files, blank links filled, unresolved
labels, metadata flags added or repaired, and the backup result.

## Safety

- Never bypass authentication, cookies, paywalls, or access controls.
- Never replace a nonblank metadata link automatically; a verified replacement
  requires explicit user approval.
- Never destroy an invalid citation file unless replacement data has already
  resolved and validated.
- Never mark `citation_exist: true` unless the matching `citation.csl.json` is valid.
- Treat `citation.csl.json` as one CSL object, not a one-item array.
- Keep organizer post-processing best-effort; citation failure never invalidates
  an otherwise organized paper.
