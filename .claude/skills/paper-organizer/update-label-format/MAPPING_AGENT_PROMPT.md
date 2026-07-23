# Mapping-agent instructions

The root agent should append one input path, one output path, and the chosen
naming specification to this prompt.

```text
You own exactly one paper-label mapping batch. Read every JSONL row from the
assigned input and write exactly one corresponding row to the assigned output.
Do not edit the source library, other batches, the consolidated manifest, or
framework files.

For every row:
- Preserve all input fields.
- Set action to rename or preserve.
- Set proposed_label to the exact final ASCII label.
- Set confidence to high, medium, or low.
- Add a concise note when authors, year, topic word boundaries, acronym casing,
  or a suffix requires judgment.
- Add review_flags for missing/corrupt metadata, author-count corrections,
  metadata/old-label year conflicts, uncertain topics, possible duplicates,
  existing timestamp suffixes, and any collision.

Apply the chosen convention exactly. Derive author components and year from
metadata. Retain the existing topic meaning; use the title, abstract, and tags
only to recover word boundaries, familiar acronyms, or enough discriminating
words to distinguish different papers. Do not invent a new subject.

Check possible duplicates by title, authors, year, DOI/URL, abstract, created
date, and local PDF hashes. Do not merge or delete anything. If two rows are
the same bibliographic paper, flag both for root review; do not independently
choose which gets the base label. If they are distinct papers, propose
descriptive non-colliding topic labels and explain the distinction.

Validate before finishing:
- output row count equals input row count;
- every old_label appears exactly once;
- all source fields are unchanged;
- every rename target matches the safe-label rule;
- proposed labels are unique case-insensitively within the batch;
- no assigned row is omitted.

Report the output path, row count, uncertain rows, and every suspected
cross-batch collision to the root agent.
```
