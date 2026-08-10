# Phase 0 summary

All six Phase 0 agents (docs/build-plan.md) have run. Full detail is in each linked file — this is the status index only. **Phase 1 has not been started.**

| # | Task | File | State |
|---|---|---|---|
| 1 | Role-scoping decision | [phase0-role-scoping.md](./phase0-role-scoping.md) | **DONE** — both pair counts now exact (updated below) |
| 2 | Riot API access | [phase0-riot-api-access.md](./phase0-riot-api-access.md) | **NEEDS-HUMAN** |
| 3 | Model bake-off | [phase0-model-bakeoff.md](./phase0-model-bakeoff.md) | **DONE** |
| 4 | Precompute throughput benchmark | [phase0-precompute-benchmark.md](./phase0-precompute-benchmark.md) | **DONE** |
| 5 | pgserver reliability spike | [phase0-pgserver-spike.md](./phase0-pgserver-spike.md) | **DONE** |
| 6 | Riot policy check | [phase0-riot-policy-check.md](./phase0-riot-policy-check.md) | **NEEDS-HUMAN** |

## Non-DONE items: exact required action

**#2 — Riot API access → NEEDS-HUMAN**
Action: log into the Riot Developer Portal (`https://developer.riotgames.com`), click "Register Project," and submit the production API key application using the drafted justification paragraph in the file. Requires a human Riot account and form submission — explicitly out of scope for an agent per the Phase 0 ground rules. A fallback dataset (Kaggle, "League of Legends(LoL) Matches Patch 25.19+") was confirmed live and is ready to bootstrap the pipeline while the key is pending.

**#6 — Riot policy check → NEEDS-HUMAN**
Action: same Developer Portal, register the specific unofficial LCU endpoint in use (`/lol-champ-select/v1/session`) — Riot's own League Client API docs require this ("leave a note on your existing application... which endpoints you're using and how"). Conclusion was AMBIGUOUS-leaning-permitted (LCU automation isn't banned, but current live policy text doesn't confirm this specific endpoint is on the approved list without that registration step).

## Follow-up closed since original Phase 0 run

**#1 — Role-scoping**: originally the same-lane pair count was a directional estimate (~2,500-3,000), flagged as a small non-blocking data-pull task for Phase 1. That follow-up ran in two passes. First pass (`docs/decisions/phase1-role-pair-count.md`, real HTTP+JSON parsing + empirical role aggregation over ranked-match data, >5% role-viability threshold): same-lane pairs = 9,204 — 3.1–3.7x higher than the original estimate. A correction surfaced along the way: an initial real parse of Data Dragon's `champion.json` returned 233 champions, but 60 of those keys are `Jade_*` game-mode-variant duplicates of existing champions, not new ones; the corrected champion count is **173**, matching the original wiki-sourced figure in `phase0-role-scoping.md` exactly (this didn't affect the pair count, which came from real ranked-match role data, not the raw `champion.json` key count). Second pass (`docs/decisions/phase1-role-threshold-sensitivity.md`): tested whether 5% was actually the right threshold, by sweeping 5/10/15/20% and checking plausibility against 10 known champions. 5% turned out too permissive — it counted implausible roles (e.g. mid/support Gragas off a 7-8% appearance share) as "viable." **>10% is the threshold that passed the plausibility check, giving the then-current figure: same-lane pairs = 6,500, exact.** All downstream docs (`phase0-role-scoping.md`, `phase0-precompute-benchmark.md`, `tiered-fallback-design.md`, `build-plan.md` Phase 3) were updated to 6,500 at that point.

**UPDATE — data-quality fix found, combined with the threshold fix:** `docs/decisions/phase1-role-pair-count-corrected.md` found the source dataset behind 6,500/9,204 was not filtered to ranked solo/duo and had ~37% duplicate rows. `docs/decisions/phase1-final-pair-count.md` combined that fix with the >10% threshold (two sanity checks, both passed exactly) and got **6,512**, not 6,500 — a 12-pair (0.18%) move. **Current figure: same-lane pairs = 6,512, exact.** All downstream docs (`phase0-role-scoping.md`, `phase0-precompute-benchmark.md`, `tiered-fallback-design.md`, `build-plan.md` Phase 3) have since been updated to 6,512.

A separate, still-open follow-up (`docs/decisions/phase1-followup-summary.md`): a real GPU (4090) throughput benchmark was attempted and came back **BLOCKED** — this session's machine has no NVIDIA GPU/CUDA, so vLLM (the tool Phase 3 actually specifies for precompute) cannot run here. The MPS numbers below remain the only real measurement available and are explicitly non-representative of target hardware.

## Key finding carried forward from #3 + #4, updated with the exact pair count

Model bake-off picked **Qwen/Qwen3-4B-Instruct-2507**. The throughput benchmark (measured on this machine's Apple Silicon MPS, explicitly **not** representative of the target 4090) found precompute at **3.36 tok/s**, giving wall-clock estimates of **~5,725h for all-pairs (14,878, exact)** and **~2,505.8h (104.4 days) for same-lane (6,512, exact — per `docs/decisions/phase1-final-pair-count.md`'s combined data-quality + threshold fix; superseded: 2,501.2h/104.2 days at 6,500 pre-data-fix, an earlier 962–1,154h estimate, then a superseded 3,541.7h/9,204 intermediate figure)** — neither fits a ~2-week refresh cadence, and same-lane is now ~7x over cadence rather than the ~3x originally reported. Recommendation from Agent 4, still standing: adopt the tiered fallback (architecture-evaluation.md rec 4, detailed in `docs/decisions/tiered-fallback-design.md`) as the primary design now, and re-run this benchmark on the actual 4090 before Phase 3 is built, since MPS and a 4090 are different batching regimes (this benchmark's own sweep found batching gave almost no speedup on MPS, which a bandwidth-bound 4090 likely would not replicate) — that re-run is currently BLOCKED on hardware access, per above.

## Environment deviations from docs, disclosed

This session ran on an Apple Silicon Mac (no NVIDIA GPU, no CUDA) rather than the 4090 described throughout docs/. Every agent that needed to run a model (#3, #4) states this plainly in its own output and labels its numbers accordingly — they are real measurements on this hardware, not simulated, but not the target-hardware numbers the build plan ultimately needs. Model weight downloads (~19GB, #3) and the `pgserver` package install (#5) were explicitly confirmed with the user before proceeding, per the Phase 0 ground rules' download/install gate.

## Scope discipline

No Phase 1 work was started. No file was created or modified outside what each task's boundary allowed, with two exceptions handled directly by the orchestrator rather than the subagent: `phase0-role-scoping.md`, `phase0-riot-api-access.md`, and `phase0-riot-policy-check.md` were written by the orchestrator using the assigned research agent's fully-cited findings, because the `research-analyst` agent type used for tasks #1, #2, and #6 has no file-write tool — the research and citations are the subagent's, the file write is a mechanical pass-through of that content, not new analysis.
