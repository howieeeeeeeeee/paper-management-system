# Browser download over the school VPN (gstack)

## Boundary — read first

This path is for **legitimate access only**:

- open-access / working-paper sources (arXiv, NBER, SSRN, RePEc, Unpaywall OA), and
- paywalled publishers (JSTOR, ScienceDirect/Elsevier, Springer, AEA, ACM, …)
  reached through the **user's own institutional/school VPN entitlement**.

The local gstack Chromium runs on the user's machine, so it inherits the VPN and
reaches the publisher exactly as the user's own authenticated browser would.

**Never** use, suggest, or implement Sci-Hub, LibGen, or any other
paywall-circumvention service. If a paper is neither free nor reachable through
the user's institutional access, **stop**: the sidecar is already written; report
"PDF unavailable" and move on.

## Is gstack available?

gstack is an **optional** backend. Detect it (prefer the repo-local copy so it
travels with PaperHub):

```bash
PAPERHUB_ROOT=$(cd paperhub_utils && cd .. && pwd)
for cand in "$PAPERHUB_ROOT/.claude/skills/gstack" "$HOME/.claude/skills/gstack"; do
  [ -d "$cand" ] && GSTACK_DIR="$cand" && break
done
echo "${GSTACK_DIR:-NONE}"
```

- If `NONE`, gstack isn't installed. Fall back: offer the **working-paper**
  version (`--mode open-access`), or ask the user to download the PDF manually
  into `to_be_organized/` (the sidecar + landing URL are ready) and continue.
- One-time setup (if the user wants the browser path): gstack needs the **Bun**
  runtime + **Playwright Chromium**, and its `browse` binary must be built. See
  the repo README's "Browser backend (optional)" note. You can also drive the
  browser by invoking the available **gstack** skill directly.

Resolve the `browse` binary via gstack's own resolver and confirm it's built:

```bash
B=$("$GSTACK_DIR/browse/bin/find-browse" 2>/dev/null)
if [ -z "$B" ] || [ ! -x "$B" ]; then
  echo "gstack 'browse' is not built. One-time setup (needs the Bun runtime):"
  echo "  cd \"$GSTACK_DIR/browse\" && ./setup"
  # Until then, the browser path is unavailable — use the working-paper version
  # (--mode open-access) or ask the user to download the PDF manually.
fi
```

`find-browse` returns the compiled `dist/browse`. If Bun isn't installed or
`./setup` hasn't run, `$B` won't resolve — fall back gracefully; do not try to
hand-build it. Call the resolved binary `$B` below.

## Cookie-bridge recipe (robust download)

gstack's `pdf` command prints the *rendered page*, not the article, and there's no
plain "save file to path" command — so authenticate in the browser, then hand the
authenticated cookies to the fetcher's validated downloader on the same VPN'd
host.

```bash
# 1. Seed the institutional session from the user's real, logged-in browser.
$B cookie-import-browser chrome --domain .sciencedirect.com   # publisher-specific

# 2. Open the resolved landing page (from browser_hint.landing_url / the DOI).
$B goto "https://doi.org/<DOI>"

# 3. If a login / SSO / "choose your institution" / CAPTCHA wall appears:
$B handoff "Publisher login or CAPTCHA — please sign in via school SSO, then I'll resume"
$B resume      # back to headless with the authenticated session

# 4. Locate the actual PDF link (publisher-specific):
$B links | rg -i '\.pdf|/pdf|pdfft|download'
#   ScienceDirect: a pdfft/"Download PDF" link · Springer: /content/pdf/<doi>.pdf
#   JSTOR: /stable/pdf/<id>.pdf · ACM: /doi/pdf/<doi> · AEA: aeaweb.org …pdf
#   (if it's a JS button, use `$B snapshot -i` to get an @ref and `$B click @e<N>`)

# 5. Export the authenticated cookies and download via the fetcher (validates %PDF):
$B cookies > /tmp/ph_cookies.json
cd paperhub_utils && uv run python -m scripts.paper_fetcher \
  --url "<PDF_URL>" --cookies /tmp/ph_cookies.json --stem "<stem>" --mode open-access
```

Use the **same `stem`** as the citation-only call wrote (strip `.citation.md`
from `sidecar_path`) so the PDF and sidecar stay paired.

### Fallback if the cookie-bridge fails (header-bound sessions)

Fetch the bytes inside the page context and write them yourself:

```bash
$B js "await fetch('<PDF_URL>').then(r=>r.arrayBuffer()).then(b=>btoa(String.fromCharCode(...new Uint8Array(b))))" > /tmp/ph_pdf.b64
# then base64-decode /tmp/ph_pdf.b64 to to_be_organized/<stem>.pdf (e.g. `base64 -d`)
```

## Verify before handing off

```bash
test -f "to_be_organized/<stem>.pdf" && head -c 5 "to_be_organized/<stem>.pdf" | rg -q '%PDF' \
  && echo "PDF OK" || echo "FAILED: not a PDF (likely an HTML paywall/login page)"
```

On `FAILED`: re-try after a `handoff` (auth issue), or fall back to the
working-paper version, or stop at the sidecar. Then return to the calling mode's
handoff step.
