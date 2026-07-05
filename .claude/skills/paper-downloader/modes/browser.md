# Mode: browser (VPN / institutional access)

Goal: download the **real paywalled journal PDF** through the user's own
institutional access, using the local gstack browser (which inherits the school
VPN). Use when the user says it's on JSTOR/ScienceDirect/Springer/AEA, that it's
paywalled, or that they have school access.

## Steps

1. **Get metadata + the landing URL first** (also writes the sidecar):

   ```bash
   cd paperhub_utils && uv run python -m scripts.paper_fetcher <source> --citation-only
   ```

   From the JSON, note `sidecar_path` (→ derive `stem`), `metadata.doi`,
   `browser_hint.landing_url`, and `browser_hint.publisher`.

2. **Drive the browser.** Read `shared/browser_download.md` and follow the
   cookie-bridge recipe to download the real PDF to
   `to_be_organized/<stem>.pdf`. Handle login/SSO/CAPTCHA with `handoff` →
   `resume`. Verify the saved file starts with `%PDF`.

3. **On success** → read `shared/handoff_to_summarizer.md`.
   **On failure** (no institutional access, hard CAPTCHA, publisher blocks it) →
   offer the free working-paper fallback:

   ```bash
   cd paperhub_utils && uv run python -m scripts.paper_fetcher <source> --mode open-access --stem <stem>
   ```

   If that also yields nothing, stop at the sidecar and report clearly.

## Boundary

Institutional/VPN access and open-access only. **No Sci-Hub / LibGen / paywall
circumvention** — see the boundary statement at the top of
`shared/browser_download.md`.
