# Phase 1 follow-up summary — GPU benchmark + exact same-lane pair count

**UPDATE:** AGENT-B's 9,204 figure below (5% role-viability threshold) was subsequently checked for sensitivity in `docs/decisions/phase1-role-threshold-sensitivity.md`, which found 5% too permissive against a plausibility check and recommended >10% instead — same-lane pair count became **6,500**, not 9,204. This was propagated into `tiered-fallback-design.md`, `phase0-role-scoping.md`, `phase0-precompute-benchmark.md`, and `build-plan.md`.

**UPDATE 2:** a data-quality bug (source dataset not filtered to ranked solo/duo, ~37% duplicate rows) was then found and combined with the >10% threshold in `docs/decisions/phase1-final-pair-count.md` (two sanity checks, both passed exactly) — **current same-lane pair count is 6,512**, not 6,500 or 9,204. `tiered-fallback-design.md`, `phase0-role-scoping.md`, `phase0-precompute-benchmark.md`, and `build-plan.md` now all carry 6,512, not 6,500. This file is kept as-is below as the historical record of what AGENT-A/AGENT-B actually did and found in this task run; it is not the current source of truth for the pair count.

Two agents, run per the system contract in this session. Neither modified `tiered-fallback-design.md`, `phase0-role-scoping.md`, or `phase0-precompute-benchmark.md` — propagating these numbers into those docs is a separate, later step, out of scope here.

| Agent | Task | State |
|---|---|---|
| AGENT-A | GPU precompute benchmark (vLLM, real NVIDIA GPU) | **BLOCKED** |
| AGENT-B | Exact same-lane pair count | **DONE** |

## AGENT-A — BLOCKED

**Reason:** this machine has no NVIDIA GPU. Confirmed directly this session: `nvidia-smi` not found, `torch.cuda.is_available()` → `False`, `uname -a` reports Darwin/arm64 (Apple Silicon Mac). vLLM requires CUDA and cannot run here. Per the task's own tool_requirement ("If vLLM will not run here: BLOCKED with the specific error. Do not silently substitute `transformers.generate()`") and HALT_CONDITIONS ("vLLM cannot run on this machine's CUDA setup"), the agent was not spawned to rediscover a fact already established earlier in this session (the same CUDA absence Phase 0's Agent 4 hit) — re-running the check here confirmed it's still true, and the task halted immediately rather than burning a run on it.

**What would unblock it:** running this benchmark on an actual CUDA-capable machine (the 4090 the docs assume). Phase 0's MPS-measured numbers (`docs/decisions/phase0-precompute-benchmark.md`) remain the only real throughput measurement available; they are explicitly flagged there as non-representative of target hardware, and that flag still stands.

## AGENT-B — DONE

**Headline: exact same-lane pair count = 9,204** — replacing the earlier 2,500–3,000 estimate. This is **3.1x–3.7x higher** than that estimate.

Supporting numbers (from `docs/decisions/phase1-role-pair-count.md`, all computed from real fetched/downloaded data this session):
- Champion count: **173** (Data Dragon patch 16.15.1, fetched with `curl` + `python3 json.load()` — a real parser, not an LLM-summarized fetch — repeated 3x with identical raw results, unlike Phase 0's inconsistent 159/214/328 from the same-style file). The raw parse returned 233 top-level keys; 60 of those are `Jade_*`-prefixed game-mode-variant entries (same champion, rebalanced kit for a specific mode — e.g. `Jade_Ahri` shares Ahri's numeric key and name), not distinct champions. 233 − 60 = 173, matching the wiki-sourced figure in `phase0-role-scoping.md` exactly. See `phase1-role-pair-count.md` §1 for the verification.
- Role data: Hugging Face dataset `BoostedJonP/league_of_legends_match_data`, 24,483 player-match rows, empirical `team_position` distribution per champion, 5% viability threshold, Emerald-rank-only (stated as a limitation).
- Per-role viable-champion counts (k) and C(k,2): TOP 74→2,701, JUNGLE 60→1,770, MIDDLE 71→2,485, BOTTOM 35→595, UTILITY 58→1,653. Summed, no cross-role dedup: **9,204**.

**Resolved during this task (corrects an earlier draft of this summary):** the 233-vs-173 champion count gap was not a methodology conflict between two sources — it was 60 undeduped `Jade_*` mode-variant keys in the raw Data Dragon parse, resolved in `phase1-role-pair-count.md` §1. 173 is the canonical champion count; 233 was never a competing final answer, just an intermediate raw-key count before filtering.

## Net effect on the precompute-viability question

AGENT-A could not produce a real GPU number, so Phase 0's conclusion ("full precompute doesn't fit a 2-week cadence") is neither confirmed nor overturned by new hardware data — it stands unchanged, pending an actual CUDA-capable run.

AGENT-B's exact count makes the same-lane tier's true size *worse* than assumed, not better: at Phase 0's measured (MPS, non-representative) 3.36 tok/s and 387.88 avg tokens/blurb, 9,204 pairs × 4 rank brackets × 3 phases works out to roughly 3.6x Phase 0's same-lane wall-clock estimate (i.e., well over 100 days at that throughput, not 40–48). This sharpens `tiered-fallback-design.md`'s existing point (eager tier must be a small, throughput-budget-sized fraction of same-lane pairs, not most of them) — it does not change the design itself, per this task's scope boundary.
