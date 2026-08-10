# Phase 0 — Riot production API key application (materials only) + fallback dataset

**Task:** prepare materials for a Riot production API key application and identify a fallback public dataset. Per Phase 0 ground rules, no application was submitted, no account was created, and no web form was filled out or submitted in this session.

## 1. Drafted application justification paragraph

This application is for a free, non-commercial, single-user desktop tool that gives League of Legends players rank-aware champion-matchup advice during champion select. It runs entirely on the player's own machine (a local FastAPI backend behind a Tauri-packaged desktop shell), reads live champ-select state from the League client's own local (unofficial LCU) API, and separately pulls public ranked match history via Match-V5 and rank-tier data via League-V4 to build an aggregated, rank-segmented, phase-by-phase (early/mid/late) matchup stats database offline, on a manual refresh the user triggers between play sessions (roughly aligned to Riot's patch cadence). A small locally-hosted language model turns those aggregated stats into precomputed advice text; nothing is generated live from Riot data during a match. This is a single product tied to a single developer/user, with no other users, no hosted service, no reselling or repackaging of Riot data for third parties, and no charge for access — i.e., no data brokering and no monetization requiring prior written approval under Riot's developer policy.

(Source docs for this description: `docs/adr-001-architecture.md`, `docs/system-design.md`, `docs/tech-stack.md`.)

## 2. Riot production API key application URL

Fetched and confirmed live this session: **`https://developer.riotgames.com`** — the Riot Developer Portal home page. Riot's own guidance (quoted below, from a source that itself links directly to this same portal home page URL) describes this as the place where the application starts:

> "You can apply for a personal or production app by clicking 'Register Project' on the main dev portal [page](https://developer.riotgames.com/)."
— [Your Application — Riot API Libraries documentation](https://riot-api-libraries.readthedocs.io/en/latest/applications.html) (fetched live this session)

Direct WebFetch of `https://developer.riotgames.com` itself succeeded (page is live, returns the portal homepage with a "Sign Up Now" / login flow and links to `/getting-started.html` and `/apis`), but the fetched content did not surface the literal button label/href for "Register Project" in a form that could be quoted verbatim — that requires an authenticated portal session (WebFetch was redirected to Riot's OAuth login at `auth.riotgames.com` when probing `/login`/`/app-type`, and the DevRel support article at `support-developer.riotgames.com/hc/en-us/articles/22801383038867-Production-Key-Applications` returned HTTP 403 to an unauthenticated fetch). This is a normal consequence of the portal requiring login before the registration form is reachable, not a broken link — the correct, confirmed-live starting URL is `https://developer.riotgames.com`.

Also confirmed live via search (not fetched due to 403, so not quoted as source text, listed for reference only): `https://support-developer.riotgames.com/hc/en-us/articles/22801383038867-Production-Key-Applications`.

Per search-derived context (not independently fetched/quoted, flagged as secondary): production keys require a completed or near-complete product, hosted on a domain the applicant owns (for ToS/Privacy Policy visibility and ownership verification), and review takes roughly two weeks (10 business days). This app has no hosted domain yet (it's a local desktop app) — worth resolving before submission; a minimal project page (GitHub repo or simple static page) may be needed to satisfy this requirement. **This detail should be re-verified by a human directly on the logged-in portal before submitting**, since it was not fetched and quoted from a live authenticated source this session.

## 3. Fallback public dataset (confirmed live)

Confirmed live via WebFetch this session:

**"League of Legends(LoL) Matches Patch 25.19+"** — Kaggle dataset by user `nathansmallcalder`.
URL: `https://www.kaggle.com/datasets/nathansmallcalder/lol-match-history-and-summoner-data-80k-matches`

WebFetch successfully retrieved this page and returned its title, "League of Legends(LoL) Matches Patch 25.19+", confirming the page is currently live and accessible. Per the search-result snippet surfaced alongside it (not independently fetched/quoted as page body text, flagged as secondary), it is described as containing 270,000+ League matches with summoner data. **A human should re-open this URL directly to confirm current row counts, license terms, and last-updated date before treating it as the pipeline's bootstrap source**, since the full page body (description, size, license) could not be extracted through WebFetch's summarized output — only the title was confirmed.

Other named candidates surfaced via search but not independently fetched/confirmed live this session (listed for reference, not verified):
- `kaggle.com/datasets/jakubkrasuski/league-of-legends-ranked-match-data-season-15`
- `kaggle.com/datasets/datasnaek/league-of-legends`
- `kaggle.com/datasets/paololol/league-of-legends-ranked-matches`

Only the `nathansmallcalder` dataset above was actually fetched and confirmed responsive in this session; treat the others as unverified leads only.

## Final state: NEEDS-HUMAN

Human actions required, none performed in this session:
1. Log into the Riot Developer Portal at `https://developer.riotgames.com`, click "Register Project," and submit the production API key application using the justification paragraph above (adjust once a hosted project domain, if required, is confirmed on the logged-in portal).
2. Confirm the `nathansmallcalder` Kaggle dataset's license and full metadata directly (page title confirmed live; full body not extracted by tooling), and download it if adopted as the pipeline's bootstrap fallback while the production key is pending.

No Riot account was created, no form was submitted, and no dataset was downloaded in this session, per Phase 0 ground rules.
