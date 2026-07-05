# Resolving the input

Classify the user's input, normalize it to a `paper_fetcher.py` source flag, and
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
2. Extract entries: each useful line matches `^\s*-\s*\[\[([^\]]+)\]\]` — the capture group is a **paper label** like `enkeetal2025behavioralattenuation`. Ignore the trailing `- reason` text (it's a human note, but you may use it as a tie-breaker).
3. Expand each label into a query (below), confirm low-confidence matches, then fetch each in the chosen mode. Continue on error — one failure must not abort the batch. Summarize per-label outcomes at the end.

### Label expansion

A label matches `^([a-z]+?)(etal)?(\d{4})([a-z_]+)$`:

- **author run** = the leading lowercase letters (a surname, or several surnames concatenated). The literal `etal` token means "et al." — drop it.
- **year** = the four digits.
- **topic** = the trailing `[a-z_]+`, split on `_` into keywords.

Build the search as `--title "<topic words>" --author "<first surname>" --year <year>`.
Example: `enkeetal2025behavioralattenuation` → `--title "behavioral attenuation" --author enke --year 2025`.

This is heuristic. **Always show the top candidate (title / authors / year) and confirm** before downloading in batch, unless the user explicitly said "just grab them all". Surname runs for multi-author labels are imperfect; lean on the topic words + year for matching and use the reason note to disambiguate.

## After fetching a batch item

If the user later wants the `papers to find.md` entry checked off or annotated,
**ask before editing that file** — it's a user document. (See the note in
`modes/citation_only.md`.)
