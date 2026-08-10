# Phase 0 — Riot policy check: local LCU automation

**Task:** confirm whether current Riot developer policy prohibits, permits, or leaves ambiguous local League-client (LCU) automation — reading the local lockfile and polling `https://127.0.0.1:<port>/lol-champ-select/v1/session` — for a free, non-commercial, single-user tool. This is distinct from the public Match-V5/League-V4 API.

**Method:** fetched live via WebFetch this session: `developer.riotgames.com/policies/general`, `developer.riotgames.com/terms`, `developer.riotgames.com/docs/lol`, `developer.riotgames.com/league-client-apis.html`, and Riot DevRel's LCU policy announcement at `riotgames.com/en/DevRel/changes-to-the-lcu-api-policy`.

## Relevant clauses (quoted, with source)

**`developer.riotgames.com/docs/lol` / mirrored at `league-client-apis.html`** (League Client API / LCU docs):
> "This service is not officially supported for use with third party applications."

> "We provide no guarantees of full documentation, service uptime, or change communication for unsupported services."

> "Either create a new application or leave a note on your existing application in the Developer Portal. We need to know which endpoints you're using and how you're using them."

**`riotgames.com/en/DevRel/changes-to-the-lcu-api-policy`** (DevRel announcement):
> "Before you release an application... that uses the League Client API in any region, you must contact us and let us know."

> "Only endpoints on our approved list are allowed for use by developers."

The fetched page summarizes rather than reproduces the full approved-endpoint list, so this session could not confirm whether `/lol-champ-select/v1/session` specifically is on that approved list. This is the single concrete gap in this check.

**`developer.riotgames.com/policies/general`:**
> "Products should use supported services from Riot Games for data ingestion." (a stated preference, not an outright ban — and the LCU docs above explicitly provide a registration path for it rather than prohibiting it outright)

Also requires one product per API key. Monetization/charging restrictions are conditioned on charging for access, which doesn't apply to this free single-user tool.

Neither `/policies/general` nor `/terms` currently contains the word "broker" as of this fetch — the data-broker clause referenced in `docs/adr-001-architecture.md`'s Trade-off Analysis section could not be verified against the current live policy text and should be treated as unconfirmed/possibly stale until re-sourced.

## Conclusion: AMBIGUOUS

Local LCU automation is not prohibited outright — Riot's own docs describe it as an unsupported-but-permitted-with-registration service, not a banned one. But it is gated on a specific step this session could not complete: **registering the specific LCU endpoint(s) in use (`/lol-champ-select/v1/session`) via the Riot Developer Portal**, per the docs' own instruction ("leave a note on your existing application... which endpoints you're using and how"). Without that registration, and without visibility into the actual current approved-endpoint list, it can't be confirmed as fully PERMITTED.

**What's unclear:** whether `/lol-champ-select/v1/session` is currently on Riot's approved LCU endpoint list.

**What would resolve it:** register the application on the Riot Developer Portal (the same portal used for the production API key application, see `docs/decisions/phase0-riot-api-access.md`) and note the specific LCU endpoint being used, per the LCU docs' own instructions. This is a NEEDS-HUMAN action — it requires a Riot developer account and portal submission, same as the production API key application.

## Final state: NEEDS-HUMAN

Human action required: register the app and the specific LCU endpoint (`/lol-champ-select/v1/session`) via the Riot Developer Portal, per `developer.riotgames.com/docs/lol`'s own registration instructions. This was not submitted in this session — no account creation or form submission was performed, per Phase 0 ground rules.
