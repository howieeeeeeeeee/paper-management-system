---
name: citation-resolver
description: Audit or resolve PaperHub citation coverage for exact labels or Boolean tag selections. Triggers on checking citation coverage, counting papers needing links or citation data, or creating/repairing citation.csl.json. Audit is read-only; apply requires explicit user intent.
---

# Citation Resolver

Open `.claude/skills/citation-resolver/SKILL.md` from the PaperHub root and
follow its canonical workflow. Use `paperhub_utils/scripts/paper_select.py` for
deterministic selection and `paperhub_utils/scripts/citation_resolver.py` for
read-only audit or explicit best-effort resolution. Never turn an audit into an
apply operation, replace a nonblank metadata link without showing a verified
replacement and obtaining explicit user approval, or bypass access controls.
