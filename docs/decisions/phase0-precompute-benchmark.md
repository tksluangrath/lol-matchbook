# Phase 0 — precompute throughput benchmark

**Date:** 2026-08-06
**Task:** build-plan Phase 0, "Real throughput benchmark: batched generation speed for the chosen model … to get an actual precompute wall-clock estimate."
**Model:** `Qwen/Qwen3-4B-Instruct-2507` (per [phase0-model-bakeoff.md](./phase0-model-bakeoff.md)), loaded from the local HF cache — no re-download.
**Status:** Measured. **Full precompute is not viable on this hardware — same-lane pairs updated to the exact count at the recommended role-viability threshold (6,512, combining the >10% threshold with a data-quality fix — ranked-only filter + dedup — per phase1-final-pair-count.md; was estimated 2,500–3,000, then an intermediate 9,204/9,177 at a too-permissive threshold, then 6,500 at 10% on uncorrected data — see phase1-role-threshold-sensitivity.md and phase1-final-pair-count.md) and it is still ~7x over a two-week cadence. The tiered fallback (architecture-evaluation recommendation 4) is required, and the benchmark must be re-run on the 4090 before the timeline is trusted either way.**

**UPDATE:** `docs/decisions/phase1-final-pair-count.md` combined the >10% threshold with a data-quality fix (the source CSV was not pre-filtered to ranked solo/duo and contained ~37% duplicate rows) and found the same-lane count is **6,512**, not 6,500 — a 12-pair (0.18%) move, essentially unchanged. All same-lane figures below are recomputed against 6,512; the 6,500 figures are kept for the record immediately below each, not deleted.

## Hardware caveat — read this before quoting any number below

**This is an Apple Silicon Mac (arm64, `Mac16,1`, 16GB unified memory), MPS backend. There is no NVIDIA GPU and no CUDA on this machine.** Every tokens/sec figure here is real, measured Apple Silicon MPS throughput. It is **not** 4090 throughput and must not be presented as such. The docs' target hardware is a 24GB 4090, which has both far more memory bandwidth and — critically for this benchmark — a batching profile that Apple Silicon does not share (see "Why batching didn't help" below). The wall-clock estimates in this document are therefore a **floor on how bad it can be**, not a prediction for the target box. The benchmark has to be re-run on the 4090.

## Setup

| | |
|---|---|
| Hardware | Apple Silicon `Mac16,1`, 16GB unified memory, arm64 macOS |
| Backend | MPS (`torch.backends.mps.is_available()` → `True`), `dtype=torch.bfloat16`, unquantized |
| Stack | `torch` 2.11.0, `transformers` 5.3.0, batched `model.generate()` |
| Model load | from local HF cache (`models--Qwen--Qwen3-4B-Instruct-2507`, 7.5GB), 9.4s to load — excluded from all timings |
| Generation | `max_new_tokens=400`, `do_sample=False` (greedy), left-padded batch, single `generate()` call |
| Prompts | 8 matchup-advice prompts in bake-off style: `"Write {phase} advice for {A} vs. {B}, {lane}, at {rank} rank."` varied across 8 champion pairs × 3 phases × 4 rank brackets, plus the bake-off's system prompt verbatim |
| Warmup | a short throwaway generation before timing, so graph-compile cost isn't counted |

## Batch size used: 8 — and why

A batch-size sweep was run first (64 new tokens each, same model instance, same prompts):

| Batch size | Wall-clock | Tokens generated | Tokens/sec | Sec/decode step | MPS allocated |
|---|---|---|---|---|---|
| 1 | 7.25s | 64 | 8.82 | 0.113 | 8.04 GB |
| 2 | 13.44s | 128 | 9.53 | 0.210 | 8.04 GB |
| 4 | 25.40s | 256 | 10.08 | 0.397 | 8.04 GB |
| 8 | 49.24s | 512 | **10.40** | 0.769 | 8.04 GB |

8 was chosen because it is the largest batch that showed any throughput gain at all before the gain flattened, and it fits comfortably in 16GB unified memory (weights are 8.04GB; KV cache at this batch/length is well under a GB). Larger batches were not pursued because the sweep shows there is nothing to win: throughput is flat from 1 → 8.

**Why batching didn't help (this is the important finding, not the tokens/sec):** per-step time scales almost perfectly linearly with batch size (0.113 → 0.769s, i.e. 6.8x for 8x the work), so total throughput is flat at ~9-10 tok/s regardless of batch size. That means decode here is **compute-bound**, not memory-bandwidth-bound. Batching is a throughput win only when decode is bandwidth-bound — you reuse one weight read across many sequences. On a 4090 that is exactly the case and batching genuinely multiplies throughput; on this laptop-class GPU it does not. **This is the single largest reason the numbers below cannot be extrapolated to the target hardware** — the 4090 doesn't just have a faster clock, it has a different scaling regime.

## Measured throughput at realistic blurb length

Full-length run, batch size 8, `max_new_tokens=400`, prompt 78 tokens:

| | |
|---|---|
| Total generated tokens | **3,103** (sum of real token counts, EOS-trimmed, padding excluded) |
| Wall-clock generation time | **923.0s** |
| **Measured tokens/sec** | **3.36** |
| Per-sequence token counts | 400, 347, 387, 400, 400, 369, 400, 400 |
| **Measured avg_tokens_per_blurb** | **387.88** (3,103 ÷ 8) |
| Sequences that hit the 400 cap | 5 of 8 |

`avg_tokens_per_blurb` is measured from the actual outputs, not assumed. Note it is a **lower bound**: 5 of 8 blurbs were still writing when the 400-token cap hit, so the model's natural blurb length for these prompts is ≥388. A shorter cap enforced in production would lower this and improve the estimate proportionally.

### Throughput degrades sharply with context length

Per-step timing was instrumented (a `LogitsProcessor` hook recording a timestamp each decode step):

| Decode steps | Wall-clock | Effective tok/s at bs=8 |
|---|---|---|
| 1–100 | 75.3s | 10.6 |
| 101–200 | 81.4s | 9.8 |
| 201–300 | 100.6s | 8.0 |
| 301–400 | **647.5s** | **1.2** |

The first 300 steps run at ~9.33 tok/s, consistent with the sweep. The last 100 steps are 6.5x slower per step than the first 100 — a cliff, not smooth KV-cache growth. This run was reproduced: an identical earlier run of the same configuration measured **2.22 tok/s** end-to-end (same 3,103 tokens, 1,400.2s), so run-to-run variance on this machine is real and the honest measured range is **2.22–3.36 tok/s**. The favorable end (3.36) is used as the headline below; the cause of the cliff (thermal throttling vs. unified-memory pressure at 16GB vs. an MPS attention-path fallback at longer sequence length) was not isolated and is a laptop-specific artifact that likely does not exist on a 24GB discrete 4090.

## Wall-clock precompute estimate

Formula, exactly as specified, with every input stated:

```
wall_clock_seconds = pair_count × 4 rank_brackets × 3 phases × avg_tokens_per_blurb ÷ measured_tokens_per_second
```

Inputs:
- `rank_brackets = 4` — fixed by docs/system-design.md, not varied.
- `phases = 3` (early/mid/late) — fixed by docs/system-design.md, not varied.
- `avg_tokens_per_blurb = 387.88` — measured this session (above), not assumed.
- `measured_tokens_per_second = 3.36` — measured this session at batch size 8 (above), not assumed. Apple Silicon MPS.

### Option A — all-pairs (pair_count = 14,878, EXACT)

Source: [phase0-role-scoping.md](./phase0-role-scoping.md) §3a — C(173,2) = 14,878, exact and cited.

```
14,878 × 4 × 3 × 387.88 ÷ 3.36
  = 178,536 generations
  = 69,250,544 generated tokens
  = 20,610,281 seconds
  = 5,725.1 hours  (238.5 days)
```

### Option B — same-lane (pair_count = 6,512, EXACT — UPDATED AGAIN)

**Update, third revision:** [phase1-final-pair-count.md](./phase1-final-pair-count.md) found the dataset behind the 6,500/9,204 figures below was not filtered to ranked solo/duo and had ~37% duplicate rows, and recomputed the >10% threshold on the corrected data: **6,512 pairs**, verified against two sanity checks (reproducing 9,177 at 5%-on-corrected and 6,500 at 10%-on-uncorrected exactly). The figures immediately below are recomputed against 6,512; the 6,500-derived, 9,204-derived, and original-estimate-derived numbers are all preserved further down for the record.

```
6,512 × 4 × 3 × 387.88 ÷ 3.36
  = 78,144 generations
  = 30,310,495 generated tokens
  = 9,020,981 seconds
  = 2,505.8 hours  (104.4 days)
```

**Update, second revision (superseded by the above, kept for the record):** this was originally computed against a directional estimate (2,500–3,000, from `phase0-role-scoping.md` §3b, which at the time stated the exact count couldn't be extracted with the tools available). [phase1-role-pair-count.md](./phase1-role-pair-count.md) closed that gap with empirical role aggregation over real ranked-match data (170 champions, `team_position` field), first at a >5% viability threshold — **9,204 pairs**. A follow-up sensitivity check, [phase1-role-threshold-sensitivity.md](./phase1-role-threshold-sensitivity.md), tested 5/10/15/20% against a plausibility spot-check (do the resulting viable roles for 10 known champions match informed-player expectations) and found 5% too permissive (e.g. it counted mid/support Gragas as "viable" off a 7-8% appearance share). **>10% passed the plausibility check: 6,500 pairs** (uncorrected data — see update above for the corrected 6,512 figure).

```
6,500 × 4 × 3 × 387.88 ÷ 3.36
  = 78,000 generations
  = 30,254,640 generated tokens
  = 9,004,357 seconds
  = 2,501.2 hours  (104.2 days)
```

*(Superseded — intermediate 9,204-derived figure, kept for the record, not current):*
```
9,204 × 4 × 3 × 387.88 ÷ 3.36
  = 110,448 generations
  = 42,840,570 generated tokens
  = 12,750,170 seconds
  = 3,541.7 hours  (147.6 days)
```

*(Superseded — original estimate-derived range, kept for the record, not current):*

Lower bound, `pair_count = 2,500` (estimate):
```
2,500 × 4 × 3 × 387.88 ÷ 3.36
  = 30,000 generations
  = 11,636,400 generated tokens
  = 3,463,214 seconds
  = 962.0 hours  (40.1 days)
```

Upper bound, `pair_count = 3,000` (estimate):
```
3,000 × 4 × 3 × 387.88 ÷ 3.36
  = 36,000 generations
  = 13,963,680 generated tokens
  = 4,155,857 seconds
  = 1,154.4 hours  (48.1 days)
```

### Sensitivity to the two soft inputs

Same formula, same fixed 4 × 3, same measured 387.88 avg tokens, only `measured_tokens_per_second` swapped:

| tokens/sec used | All-pairs 14,878 | Same-lane 6,512 (exact, current) | Same-lane 6,500 (superseded) | Same-lane 9,204 (superseded) |
|---|---|---|---|---|
| 2.22 (the slower of the two identical runs) | 8,665.0 h | 3,793.4 h | 3,785.6 h | 5,360.4 h |
| **3.36 (headline, full-run measured)** | **5,725.1 h** | **2,505.8 h** | 2,501.2 h | 3,541.7 h |
| 9.33 (pre-cliff steady state, first 300 steps) | 2,061.8 h | 902.4 h | 900.8 h | 1,275.5 h |

Even the most generous row — steady-state throughput with the degradation cliff hypothetically engineered away — leaves same-lane precompute at 902.4 hours (37.6 days). (Superseded reference: the original 2,500–3,000-estimate range at this row was 346–416 hours; the 9,204 intermediate figure pushed it to 1,275.5 hours; 6,500 landed at 900.8 hours; the current 6,512 figure is essentially identical to 6,500, 902.4 hours.)

## Is this compatible with "runs between sessions on a ~2-week patch cadence"?

docs/system-design.md §1 frames the refresh as running between play sessions, on Riot's roughly two-week patch cadence, as an explicitly user-triggered job. The usable budget is at most a few overnight windows — call it tens of hours, not hundreds. Against that:

- **All-pairs (14,878, exact count): NO. 5,725 hours (238.5 days).** This is ~17x longer than the patch cycle it's supposed to fit inside. The refresh would never finish before the next patch invalidated it. Not viable at any plausible amount of tuning.
- **Same-lane (6,512, exact count at the recommended >10% role-viability threshold on ranked-only, deduplicated data — updated from an original 2,500–3,000 estimate, then a superseded 9,204/9,177 intermediate figure, then a superseded 6,500 pre-data-fix figure): NO. 2,505.8 hours (104.4 days).** Role-scoping cuts the work by ~56% relative to all-pairs (not the ~80% the original estimate implied, and better than the intermediate figure's ~38% — see `phase1-role-threshold-sensitivity.md` for why the threshold matters: a too-permissive 5% bar counted implausible secondary roles as viable, inflating the pool), and it is still ~7x longer than the two-week cadence, not ~3x as the original estimate-based figure suggested. Role-scoping is necessary but nowhere near sufficient on this hardware. (The data-quality fix in `phase1-final-pair-count.md` moved this from 6,500 to 6,512 pairs — 0.18% — negligible next to the threshold effect.)

Restating the caveat because it changes how this conclusion should be read: **on the target 4090 these numbers will be substantially better, and possibly by more than a naive clock-speed ratio, because the sweep above shows this machine gets no benefit from batching while a 4090 does.** These figures establish that precompute definitely fails on Apple Silicon; they do not establish that it fails on the 4090. That question is still open until the benchmark is re-run there.

## What this changes downstream

1. **Adopt the tiered fallback (docs/architecture-evaluation.md recommendation 4) now, not conditionally.** The build plan lists it as "if Phase 0's throughput benchmark says full precompute is too slow" — on the only hardware actually measured, it says exactly that, twice over. Eager-precompute high-play-rate pairs, lazy generate-and-cache the long tail on first request. This also stops being pure insurance and becomes the primary mechanism until a 4090 measurement says otherwise.
2. **Re-run this benchmark on the 4090 before Phase 3 is designed around a number.** Same script, same prompts, same formula. The batching-scaling result is the specific thing to re-measure — it's what determines whether the 4090 is 5x faster or 50x faster here.
3. **Cap blurb length deliberately.** 5 of 8 blurbs hit a 400-token cap mid-sentence, so ~388 tokens is a floor on natural length. Wall-clock is exactly linear in this input; a 200-token target blurb halves every number above. Deciding a target blurb length is now a throughput decision, not just an editorial one.
4. **Closed:** the role-scoping follow-up flagged in phase0-role-scoping.md mattered more than it looked, and has since been resolved in three passes. The exact same-lane pair count (`phase1-role-pair-count.md`, `phase1-role-threshold-sensitivity.md`, `phase1-final-pair-count.md`) is **6,512** at the recommended >10% role-viability threshold on ranked-only, deduplicated data, not 2,500–3,000 (~2.2–2.6x higher), not the intermediate 9,204/9,177 figures from a too-permissive 5% threshold that failed a later plausibility check, and barely different from the pre-data-fix 6,500 figure (+12, +0.18%). Every same-lane figure above has been recomputed against 6,512; the conclusion is unchanged from the 6,500-based one (~7x over cadence, not ~3x) but better-grounded, since it also fixes the ranked-only-filter/dedup bug found in `phase1-role-pair-count-corrected.md`.
5. **Confirms the tech-stack split, again.** Unbatched-equivalent throughput on a general-purpose runtime is the wrong tool for a bulk job. docs/build-plan.md Phase 3 already says use vLLM or batched `transformers` rather than `llama-cpp-python`; on CUDA, vLLM's continuous batching is where the batching win this machine couldn't demonstrate actually shows up.

## Reproducibility

Benchmark scripts were written to the session scratchpad, not to the repo (this task's output is one file). To reproduce: load `Qwen/Qwen3-4B-Instruct-2507` in bf16 on MPS, left-pad a batch of 8 chat-templated matchup prompts with the bake-off system prompt, `generate(max_new_tokens=400, do_sample=False)`, and divide EOS-trimmed generated token count by wall-clock time around the `generate()` call with `torch.mps.synchronize()` on both sides.

DONE
