# Resolving the input

Classify the user's input, normalize it to a `scripts.paper_fetcher` source flag, and
(for a batch) expand each entry into a query.

## Single-item classification (regex, first match wins)

| Order | Input | Detection | Normalize to |
|-------|-------|-----------|--------------|
| 1 | arXiv ID | `^(arXiv:)?\d{4}\.\d{4,5}(v\d+)?$` or old-style `^[a-z\-]+/\d{7}$` | `--arxiv <id>` (strip a leading `arXiv:`) |
| 2 | DOI | `\b10\.\d{4,9}/\S+\b`; strip a leading `https://doi.org/`, `http://dx.doi.org/`, or `doi:` | `--doi <doi>` |
| 3 | URL | `^https?://` and host is not `doi.org` | `--url <url>` |
| 4 | Title/author | anything else containing spaces | `--title "<title>" [--author "<surname>"]` |

If the user wrote something like *"Coutts 2019, Good news and bad news"*, pass the descriptive part as `--title` and the surname as `--author`; the year goes to `--year`.

## Batch from `to_be_organized/papers to find.md`

Trigger when the user says "papers to find", "the list", "the backlog", "batch",
or points at that file.

1. Read `to_be_organized/papers to find.md`.
2. Extract entries: each useful line matches `^\s*-\s*\[\[([^\]]+)\]\]` — the capture group is a **paper label** such as `Enke_etal2025BehavioralAttenuation` or the legacy `enkeetal2025behavioralattenuation`. Ignore the trailing `- reason` text (it's a human note, but you may use it as a tie-breaker).
3. Expand each label into a query (below), confirm low-confidence matches, then fetch each in the chosen mode. Continue on error — one failure must not abort the batch. Summarize per-label outcomes at the end.

### Label expansion

Support both current Hybrid PascalCase labels and existing lowercase labels:

- Current format: `^([A-Z][A-Za-z]*?)(_etal)?(\d{4})([A-Z][A-Za-z0-9]*)$`.
  The author run uses PascalCase, `_etal` marks three or more authors, and the
  topic uses PascalCase with possible uppercase acronym runs.
- Legacy format: `^([a-z]+?)(etal)?(\d{4})([a-z_]+)$`. The literal `etal`
  token marks three or more authors and the topic may use underscores.

For the current format, remove `_etal`, split the topic at PascalCase and acronym
boundaries, and take the first PascalCase surname component as the author hint.
For legacy labels, remove `etal` and split the topic on underscores; when the
lowercase topic has no boundary, use it as one approximate search term. In both
formats, the four digits are the year.

Build the search as `--title "<topic words>" --author "<first surname>" --year <year>`.
Examples:

- `Enke_etal2025BehavioralAttenuation` → `--title "behavioral attenuation" --author Enke --year 2025`.
- `Huynh_etal2026LLMCooperation` → `--title "LLM cooperation" --author Huynh --year 2026`.
- `enkeetal2025behavioral_attenuation` → `--title "behavioral attenuation" --author enke --year 2025`.

This is heuristic. **Always show the top candidate (title / authors / year) and confirm** before downloading in batch, unless the user explicitly said "just grab them all". Surname runs for multi-author labels are imperfect; lean on the topic words + year for matching and use the reason note to disambiguate.

## After fetching a batch item

If the user later wants the `papers to find.md` entry checked off or annotated,
**ask before editing that file** — it's a user document. (See the note in
`modes/citation_only.md`.)
