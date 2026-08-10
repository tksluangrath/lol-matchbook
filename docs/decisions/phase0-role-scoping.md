# Phase 0 — Role-scoping decision for "matchup"

**Task:** decide whether "matchup" means same-lane opponents only or all champion pairs regardless of role, and compute exact pair counts for both, per `docs/architecture-evaluation.md`'s critical finding and `docs/build-plan.md` Phase 0.

## 1. Total champion count (n)

**n = 173**, as of today (2026-08-06).

Source: `https://wiki.leagueoflegends.com/en-us/List_of_champions` (Riot's own wiki), fetched live this session. Explicit quoted text: "As of 24 June 2026, there are 173 champions released in total." Cross-checked via WebSearch: multiple independent sources (dotesports.com, blast.tv, turbosmurfs.gg) agree the most recently released champion is **Locke, the Ashen Exorcist** (June 24, 2026), and no new champion has been released since — so 173 is still current as of today.

**Tooling caveat (important for whoever implements Phase 1):** the task instructions specified fetching Data Dragon's `champion.json` directly to get this count. That fetch was attempted — `https://ddragon.leagueoflegends.com/api/versions.json` (confirmed current patch: `16.15.1`) and then `https://ddragon.leagueoflegends.com/cdn/16.15.1/data/en_US/champion.json` — but the WebFetch tool available in this session summarizes large JSON responses through a small LLM rather than parsing them directly, and this file is large enough that three separate fetch attempts of the exact same file returned three different, mutually inconsistent counts (159, 214, and 328 — the 328 figure even included fabricated `Jade_*`-prefixed keys that do not exist in real Data Dragon output). None of those numbers are trustworthy and none are cited here as measured results. The wiki's explicit prose statement (173) is used instead because it was returned as literal quoted text, not a tool-summarized count over a large payload. **Phase 1 implementation should re-derive this count with a real JSON parser (e.g., Python `requests` + `json.load()` on `champion.json`) rather than an LLM-summarized fetch** — that will also be the authoritative source going forward since it updates every patch, whereas the wiki prose statement is a snapshot that requires manual re-checking.

## 2. Role/lane data source

**Searched for:** a reliable, freely available per-champion primary-lane-role dataset (not Data Dragon's `tags`, which is an archetype classification — Fighter/Mage/Assassin/Tank/Marksman/Support — not a Top/Jungle/Mid/ADC/Support mapping, per this task's known constraint).

**Found and fetched:** `https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data` — a Lua data module on Riot's own official wiki, which contains genuine per-champion position fields. Confirmed by direct fetch, quoted example for Ashe:
```
["client_positions"] = {"Bottom","Support"},
["external_positions"] = {"Bottom","Support"},
```
`client_positions` reflects Riot's own in-client role-select tags (the multi-select role filter shown in champion select); `external_positions` reflects third-party analytics-derived positions (meta-dependent, changes over time).

This confirms two things relevant to scoping:
- A real source for role data exists (it is Riot's own wiki, not a third party) — the "no reliable source exists" fallback in this task's known constraint does not apply here.
- Champions routinely have **more than one** valid position (Ashe = Bottom + Support). "Same-lane" pairing is therefore not a clean 1-champion-to-1-role mapping; it requires a champion-to-multiple-roles model, and "same lane" for a pair means their position sets *intersect*, not that they're equal.

**Why the full 173-champion dataset was not extracted in this session:** doing so reliably would require fetching and parsing the complete Lua module in full, and the only fetch tool available (WebFetch) already demonstrated unreliable extraction on a similarly large document (see the `champion.json` count discrepancy in section 1). Manually pulling 173 individual entries through that same unreliable extraction path would risk presenting a fabricated or partially-hallucinated number as a measured result, which is explicitly disallowed.

Also checked: `https://riot-api-libraries.readthedocs.io/en/latest/roleid.html`, which independently confirms role/lane is not a clean static attribute even from Riot's own Match-V5 API — it states the API's raw Role/Lane fields in match data are "often inaccurate," and that accurate position identification requires post-processing (simple Role/Lane mapping ≈87.5% accurate, playrate-weighted correction ≈95% accurate, or ML-based timeline analysis). This reinforces that "role" in this system is better modeled as a per-match, derived/probabilistic attribute (from Match-V5 `teamPosition`, corrected) rather than a single fixed static field per champion — relevant to the schema recommendation below.

## 3. Computed pair counts

**(a) All pairs, regardless of role:**
Unordered pairs = C(n,2) = C(173,2) = 173 × 172 / 2 = **14,878 pairs**.
Source: n=173 as established in section 1; arithmetic only, not a fetched number.

**(b) Same-lane pairs only:**
**UPDATE (Phase 1 follow-up, see `docs/decisions/phase1-role-pair-count.md`): computed exactly. Same-lane pairs = 6,500.**

**UPDATE 2 (see `docs/decisions/phase1-final-pair-count.md`): a data-quality bug in the source dataset (not filtered to ranked solo/duo, ~37% duplicate rows) was found and combined with the >10% threshold, with two sanity checks both passing exactly. Current same-lane pairs = 6,512, not 6,500** — the data fix alone moved the count by only +12 (+0.18%); the threshold change was the dominant effect.

The gap below (originally: "could not be computed") was closed by a follow-up task using empirical role aggregation over real ranked match data (Hugging Face dataset `BoostedJonP/league_of_legends_match_data`, `team_position` field, 24,483 usable rows, 170 champions present in-sample) instead of the wiki Lua module this session couldn't reliably extract. That first pass used a >5%-of-appearances role-viability threshold and got **9,204** — but a second follow-up (`docs/decisions/phase1-role-threshold-sensitivity.md`) tested that threshold's sensitivity against a plausibility check (do the resulting viable-role sets for 10 known champions match what an informed player would expect) and found 5% too permissive — e.g. it counted Gragas as viable in 4 roles including mid/support off a 7.3%/5.8% appearance share, which doesn't match real play patterns. **>10% was the threshold that passed the plausibility check for all 10 spot-checked champions**, and was the then-current figure. Per-role viable-champion counts at >10% on that (uncorrected) data (no cross-role dedup): TOP 58, JUNGLE 59, MIDDLE 59, BOTTOM 30, UTILITY 45 → C(k,2) summed across roles = 1,653 + 1,711 + 1,711 + 435 + 990 = **6,500** (superseded — see `phase1-final-pair-count.md`: on ranked-only, deduplicated data at the same >10% threshold, the count is **6,512**). Full method, the full 5/10/15/20% sensitivity table, and the plausibility spot-check are in `phase1-role-threshold-sensitivity.md`; the underlying per-role breakdown is in `phase1-role-pair-count.md`; the data-quality-corrected recomputation is in `phase1-role-pair-count-corrected.md` and `phase1-final-pair-count.md`.

This is **~2.2-2.6x higher** than the ~2,500-3,000 estimate originally left here as directional-only context (below, preserved for the record — do not treat it as current). The estimate's "30-40 viable champions per role" assumption undershot for every role at the 10% threshold too (30-59, mean ≈50), though less dramatically than the earlier 5%-threshold figure did (35-74, mean ≈60) — 10% filters out the lowest-frequency, noisiest role assignments that the estimate's informal "primary role" intuition wouldn't have counted either.

*(Original estimate, preserved for context, not current):* assuming roughly 30-40 viable champions per role across 5 roles, same-lane pairs land in the range of ~2,500-3,000 — materially smaller than the 14,878 all-pairs figure. This estimate was not verified when written and has since been superseded by the exact count above.

*(Intermediate figure, also superseded):* an earlier follow-up pass computed 9,204 at a >5% role-viability threshold, which failed the later plausibility check — see above.

## 4. Recommendation

**Scope "matchup" to same-lane opponents only.**

Reasoning:
- Per `docs/architecture-evaluation.md`'s own finding, same-lane pairing is "the only pairing that actually has 'early/mid/late lane matchup' advice to give" — a jungler vs. a mid-laner don't share a lane phase in any meaningful sense, so an early/mid/late "matchup" blurb for that pair is either vacuous or fabricated.
- The measured all-pairs count (14,878, exact, section 3a) confirms `docs/system-design.md`'s existing ~14,500-pair estimate was in the right ballpark — and at 4 rank brackets × 3 phases, that's 178,536 precompute generations, which is the exact throughput problem `docs/architecture-evaluation.md` flagged as likely infeasible (150-250 hours at naive unbatched generation speed) on a two-week patch cadence.
- Restricting to same-lane pairs is the direct lever that brings the precompute count down from 14,878 to **6,512** (section 3b, exact, at the recommended >10% role-viability threshold on ranked-only, deduplicated data — see `phase1-final-pair-count.md`; superseded: 6,500 pre-data-fix) — a real reduction, closer to the original estimate than the intermediate 9,204 figure was, but still above it (~56% fewer pairs than all-pairs, not the ~80% fewer the original 2,500-3,000 estimate implied). At 4 rank brackets × 3 phases, that's 78,144 generations for same-lane vs. 178,536 for all-pairs — same-lane is meaningfully smaller, and the actual precompute schedule still depends on real throughput numbers (`docs/decisions/phase0-precompute-benchmark.md`, `docs/decisions/phase1-followup-summary.md`) as much as it depends on scoping choice. See `docs/decisions/tiered-fallback-design.md` for how the design accounts for this.
- The cost is added schema complexity from multi-position champions (section 2) — this is real work, but strictly less work than generating and maintaining ~2.3x more precomputed rows (178,536 vs. 78,000) for pairs with no coherent lane-phase narrative to write.

## 5. Does `matchup_stats`/`advice` need a `role` column?

**Yes — regardless of which scoping option had been chosen**, because:
- `docs/system-design.md`'s data pipeline already plans to bucket by rank tier and game phase using Match-V5 data; role/position must be captured at aggregation time too, since Match-V5's `teamPosition` (or a corrected derivation of it, per the `roleid.html` source in section 2) is the only accurate way to know what lane a given champion was actually played in for a given match — it cannot be inferred from a static per-champion field, because of flex picks (section 2).
- Given the same-lane scoping recommendation (section 4), `role` (or a `lane`/`position` column) becomes part of the matchup's identity, not just a filter — the schema needs a way to represent that a champion can appear under more than one role (e.g., a `champion_role` join/lookup rather than a single `role` column on `champion`), and `matchup_stats`/`advice` rows need to key on `(champ_a, champ_b, role, rank, phase)`, not just `(champ_a, champ_b, rank, phase)`, since e.g. "Yone mid vs. Yone top" would otherwise collide in a schema without a role key.

This is a schema recommendation only — no changes were made to `app/models.py` or any other file, per this task's boundary.

## Final state: DONE — both counts now exact

The role-scoping recommendation and both requested counts are given above: (a) all-pairs is exact and cited (**14,878**), (b) same-lane is now also exact and cited (**6,512**, closed by the Phase 1 follow-ups in `phase1-role-pair-count.md`, `phase1-role-threshold-sensitivity.md`, and `phase1-final-pair-count.md`; superseded: 6,500 pre-data-fix). Recommendation: same-lane scoping. `role` column: needed regardless of scoping choice.

**Flagged follow-up, closed:** the original ask here — re-derive the champion count with a real JSON parser, and get an exact same-lane pair count via real role data rather than an estimate — was completed in `docs/decisions/phase1-role-pair-count.md`, then refined further in `docs/decisions/phase1-role-threshold-sensitivity.md`. Two corrections surfaced along the way, both worth noting: (1) a real parse of `champion.json` initially returned 233, but 60 of those keys are `Jade_*` game-mode-variant duplicates of existing champions, not new ones — corrected champion count is 173, matching the wiki figure in section 1 exactly (see `phase1-role-pair-count.md` §1). (2) the first same-lane pass used a >5% role-viability threshold and got 9,204, but a plausibility check against 10 known champions found 5% too permissive (counted implausible roles like mid/support Gragas as viable) — >10% passed the plausibility check and became the threshold, giving 6,500. (3) a further data-quality bug (source dataset not filtered to ranked solo/duo, ~37% duplicate rows) was found and combined with the >10% threshold in `phase1-final-pair-count.md`, giving the current figure: **6,512**. None of the three corrections affected the underlying method's soundness — all were caught by follow-up verification exactly as intended, not by a downstream consumer discovering a bad number.
