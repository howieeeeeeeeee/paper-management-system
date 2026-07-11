# Paper Finder

Use `paper-finder` when the paper is already in `organized/` but you only remember a claim, mechanism, author, tag, example, or snippet from any note stored with the paper.

## Find A Half-Remembered Paper

```text
\paper-finder: which paper was it where dictators avoided knowing the recipient's payoff?
```

For a deeper explanation of why each candidate matched:

```text
\paper-finder: detailed search for the moral wiggle room paper about dictators avoiding payoff information.
```

Detailed mode returns the complete metadata note, complete `ai_summary.md`, and
the complete additional Markdown notes that matched. Extra-note text is capped
at 60,000 characters per paper by default; the skill narrows detailed searches
to a small candidate set.

Paper Finder also searches personal notes inside a paper folder. For example:

```text
\paper-finder: which paper had my lecture note about selective exposure and asymmetric attention?
```

```text
\paper-finder: find the paper whose presentation note connects information acquisition to welfare.
```

Those note matches strengthen the parent paper's ranking. The lecture or
presentation note is shown as evidence, not as a separate search result.

To steer away from a neighboring literature, say what to avoid:

```text
\paper-finder: find the paper on belief updating after good news and bad news, but not the survey papers.
```

Normal output includes ranked `[[paper_label]]` candidates, trimmed metadata,
trimmed AI-summary context when available, and query-centered excerpts from
every matched additional Markdown note.
