# Citation Resolver

Use `citation-resolver` to check or complete citation records for papers already
in PaperHub. Each completed paper receives `citation.csl.json`, a standard,
machine-readable citation record stored beside its metadata note.

## Check Coverage

An audit is read-only:

```text
/citation-resolver : audit citation coverage for papers tagged behavioral_economics.
```

The result separates papers that are ready, papers with a link that still need
citation data, papers that first need a link, and papers blocked by malformed
metadata. No files change during an audit.

## Resolve Missing Records

After reviewing an audit, ask explicitly:

```text
/citation-resolver : go ahead and resolve the missing citations from that audit.
```

PaperHub rechecks the selected folders, uses existing public links when
possible, validates each paper's identity, and writes the result safely. When a
metadata link is blank, the current agent may propose a public link and fills
it only after the title and author or year match. PaperHub never automatically
replaces a nonblank link.

You can select papers by exact labels, required tags, alternative tags, or a
combination. Existing valid citation records are left unchanged unless you
explicitly request a refresh.
