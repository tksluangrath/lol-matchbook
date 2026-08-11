# Phase 2 Full-Scale Fine-Tune — AGENT-15/AGENT-16

**Status: DONE.**

This is the deferred full-scale QLoRA fine-tune named in both
`docs/decisions/phase2-implementation-summary.md` ("a separate, later,
human-triggered step requiring real GPU hardware") and
`docs/decisions/phase2-class-balance-diagnostic.md` ("the full-scale run
should use a balanced mix and more steps/epochs on GPU, not rely on
rebalancing alone").

A prior attempt at this task, on the Apple Silicon Mac used for the smoke
and balanced-diagnostic runs, is preserved below in **Prior attempt
(BLOCKED)** — that machine had no CUDA device, so it correctly halted at
AGENT-15 step 1. This run happened on a different machine, a Windows PC
with a real NVIDIA GPU, and completed both AGENT-15 and AGENT-16 for real.

## Environment verification (real, this session, this machine)

```
$ nvidia-smi
... NVIDIA GeForce RTX 2070 SUPER, driver 610.88, 8192MiB total ...

$ python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
2.11.0+cu128 True NVIDIA GeForce RTX 2070 SUPER
```

`torch` initially installed as a CPU-only wheel (no CUDA index configured);
reinstalled from `https://download.pytorch.org/whl/cu128`. `torchvision`
needed the same treatment (a stale CPU wheel caused a real
`torchvision::nms does not exist` crash on import once CUDA-torch was in
place). `peft` 0.20.0 (latest published) does not support `transformers`
5.x (`ModuleNotFoundError: BloomPreTrainedModel`, a model transformers 5.x
removed that peft's import chain still references) — pinned
`transformers==4.57.6`, which still ships it. `bitsandbytes`, `trl`,
`accelerate` installed cleanly. All 26 pre-existing unit tests plus the two
this task added passed after these fixes; see **Environment issues found
and fixed** below for detail on why each was needed.

**Resource gate:** `Qwen/Qwen3-4B-Instruct-2507` was not cached on this
machine. Downloaded for real (confirmed with the user first, per the
~500MB threshold) — 3 files fetched, model loads in ~6-15s from local cache
afterward.

**Compute gate — real 4-bit load + forward/backward pass** (not a toy
model):

```
cuda available: True
device: NVIDIA GeForce RTX 2070 SUPER
load time: 193.2s
param dtype: torch.float16
loss: 4.938388824462891
backward pass OK
VRAM allocated (GB): 3.643148288
VRAM reserved (GB): 5.559549952
4BIT_LOAD_CHECK: PASS
```

Real NF4 4-bit load via bitsandbytes, real forward pass, real backward
pass, on the actual GPU. Compute gate passed.

## Fresh data-split verification

`backend/app/finetune/data/train.jsonl` was regenerated this session via
`python -m app.finetune.qa_generation` against the real, freshly-downloaded
`BoostedJonP/league_of_legends_match_data` CSV (11,664,613 bytes, matching
the figure in `docs/decisions/phase1-role-pair-count.md` exactly). Fresh
count at the terminal:

```
total 2213, abstention 1394, non_abstention 819
```

Matches the counts cited in the task instructions and prior docs — not
assumed, reverified.

## `oversample_to_balance` (TEST_LOOP contract)

Implemented in `backend/app/finetune/train.py`, additive next to the
existing `stratified_sample` (unmodified, still passes its own tests).
Test file `backend/tests/unit/test_full_scale_oversample.py`, expected
values hand-computed from the fresh count above:

```
full_repeats = 1394 // 819 = 1
remainder    = 1394 % 819  = 575
```

Every one of the 819 real non-abstention rows appears once, plus a seeded
sample of 575 of them appears a second time — 1394 non-abstention rows
total, matching the 1394 abstention rows, for a 2788-row balanced set.

Result: **5/5 tests passed on the first attempt**, no fix-loop iterations
needed.

```
tests/unit/test_full_scale_oversample.py .....                    [100%]
5 passed
```

## Batch-size / optimizer determination (real, empirical, two rounds)

**Round 1** (`adamw_torch`, `max_length=512`, matching the smoke-run
config): `per_device_train_batch_size=4` benchmarked clean at 15 steps
(~7.45s/step, 5.26GB peak VRAM) — looked safe. It was not: the real full
run stalled at step 202/1745, per-step time exploding to 55s then 92s,
VRAM pinned at 7871/8192MB. This is the Windows NVIDIA driver's shared-GPU-
memory fallback once VRAM fills — not a Python-level OOM exception, so it
doesn't raise and can't be caught; it just goes very slow. The run was
killed rather than let it continue at that rate (would have projected
20-30+ hours). `batch_size=2` was tried next over a longer 50-step
benchmark specifically to catch this: it hit one single-step stall of
**~20 minutes** within the first 50 steps, VRAM still pinned near
7844/8192MB. `batch_size=1` was stable (4.82GB peak VRAM, clean 50/50
steps, no stalls) but too slow: real 31.78s/step average projects **~9.2h**
for the 3-epoch floor alone, over the 4-hour cap.

**Round 2** (`paged_adamw_8bit`, `max_length=256` — a real tokenizer check
showed actual training examples are 41-63 tokens max, so this truncates
nothing): `batch_size=4` completed 50/50 benchmark steps cleanly, no
stalls, steady ~6.4-6.7s/step, peak VRAM 5.23GB/8GB. This is the config
used for the committed run. The paged optimizer (not the shorter
`max_length`, which was inert given real example lengths) is the most
likely reason this stabilized — it manages optimizer-state memory
proactively instead of letting the driver's slow fallback trigger.

**Deviation from the smoke-run config, explicitly named per the task
contract:** optimizer changed `adamw_torch` → `paged_adamw_8bit`, and
`max_length` changed `512` → `256`. Both forced by the real OOM/stall
evidence above. Base model, NF4 4-bit quantization scheme, and LoRA
config (r=8, alpha=16, `[q,k,v,o,gate,up,down]_proj`) are unchanged.

## Epoch-count decision

`steps_per_epoch = ceil(2788 / effective_batch_size=8) = 349`.
At the real Round-2 benchmark rate (6.724s/step average):

- 3 epochs (1047 steps) → **projected ~1.96h**
- 5 epochs (1745 steps) → **projected ~3.26h**, still under the 4h cap

Per the task's rule (extend to 5 epochs if it still projects under 4h),
**5 epochs was chosen**.

## Training run — real wall-clock vs. projection

The committed config still hit two more large stalls during the real
1745-step run, despite the paged-optimizer fix reducing their frequency:

- Step 468→469: **~4h32m** on a single step
- A further slow stretch between step ~1044 (6h50m elapsed) and step 1737
  (16h16m elapsed)

Both were reported to the user in real time as they happened; the user
chose to let the run continue rather than kill it, given it kept
recovering to normal per-step speed afterward and loss kept decreasing
cleanly through both incidents.

```
FULL_SCALE_TRAIN_DONE wall_clock_s=58646.0
```

**Real wall-clock: ~16h17m**, against a ~3.26h projection — the projection
from a clean 50-step benchmark did not capture the intermittent VRAM-
fallback stalls that only showed up over a full 1745-step run. This GPU/
driver combination has an unresolved intermittent slowdown that neither
batch-size reduction nor the paged optimizer fully eliminated; they only
reduced how often it happens.

**Real logged loss** (174 points, every 10 steps): first `2.4447` → last
`0.1142`. Monotonic downward trend, no flat/non-decreasing failure.

## fact_ledger.md check (real, against this specific new adapter)

`backend/app/finetune/artifacts/full-scale-adapter/` — both required
checks:

```
PASS: isinstance(finetuned, PeftModel)
tensors differing from base: 252
PASS: real weight-tensor diff confirmed
FACT_LEDGER_CHECK: PASS
```

**Windows/OneDrive note:** loading the adapter's `.safetensors` file
directly from its repo path (which lives inside a OneDrive-synced folder)
crashed Python with a fatal signal inside `safetensors.torch.load_file` —
safetensors memory-maps the file, and OneDrive's cloud-sync file handling
on Windows is incompatible with that. Confirmed by reproducing the crash
against the repo path and the fix (copy to a local, non-synced temp dir
first) against a copy — not a corrupted adapter. `eval.py`'s
`load_model_and_tokenizer` now does this copy automatically for any
adapter path.

## Real bugs found and fixed en route

- **`torchvision::nms does not exist`**: stale CPU-only `torchvision`
  wheel left over from before the CUDA `torch` reinstall. Fixed by
  reinstalling `torchvision` from the same `cu128` index.
- **`ModuleNotFoundError: BloomPreTrainedModel`**: `peft` 0.20.0 (latest)
  is incompatible with `transformers` 5.x. Pinned `transformers==4.57.6`.
- **Device-mismatch crash in `eval.py`'s `generate()`**: `tokenizer(...)`
  built CPU tensors that were never moved to the model's device. Harmless
  on the Mac (CPU-only), but broke immediately once `load_quantized_model`
  became GPU-aware. Root-caused and fixed with a single `.to(model.device)`
  in the one shared `generate()` function every eval step calls through —
  not patched per call site.
- **OneDrive mmap crash** on adapter load — see fact_ledger section above.

`app.finetune.eval.load_model_and_tokenizer` and `run_all` were extended
with optional `adapter_dir`/`results_path`/`caveat` parameters (defaults
preserve the original smoke-adapter behavior exactly; the existing
`test_finetune_eval.py` suite still passes unmodified) so the full-scale
adapter could be evaluated without touching the original eval's scoring
logic. `load_model_and_tokenizer` now reuses `train.load_quantized_model`
instead of duplicating its own hardcoded CPU-only `BitsAndBytesConfig`.

## Three-way eval comparison

| | Original baseline (prior, unbalanced, 200 steps, CPU) | Balanced diagnostic (prior, balanced, 200 steps, CPU) | **Full-scale (this session, balanced, 1745 steps, real GPU)** |
|---|---|---|---|
| Held-out matchup pass rate | 0/152 (0%) | 7/152 (4.6%) | **20/152 (13.2%)** |
| Abstention pass rate | 237/237 (100%) | 207/237 (87.3%) | **186/237 (78.5%)** |

The original-baseline and balanced-diagnostic figures are cited from
`docs/decisions/phase2-implementation-summary.md` and
`phase2-class-balance-diagnostic.md` — this session did not reproduce them
(no smoke-scale or balanced-diagnostic adapter exists on this machine to
re-run); only the full-scale column is a number this session actually
generated (`backend/app/finetune/artifacts/eval_results_full_scale.json`,
step1 sanity check passed).

**Trend:** held-out accuracy keeps improving with more balanced data and
more steps (0% → 4.6% → 13.2%, real and monotonic), at the continued cost
of abstention reliability (100% → 87.3% → 78.5%). More training moves the
model further from "always hedge" toward actually attempting answers, and
each step in that direction produces more wrong non-abstentions and more
missed abstentions on the harder cases.

## Catastrophic-forgetting check (real, run for the first time — the
diagnostic explicitly skipped this)

15 general-knowledge/reasoning prompts, base vs. fine-tuned, judged for
coherence/correctness (not a scored step in `eval.py` — generation only,
scoring is this explicit judgment per the task contract):

**Base: 15/15 coherent, on-topic or in-character.**
**Fine-tuned: 13/15 — 2 real regressions**, both the *same* new failure
mode: the trained abstention hedge phrase leaking into unrelated general
prompts.

Real outputs, the two failures:

> **Prompt:** Why might a company choose to lower prices even when demand
> for its product is already high?
> **Base:** "That question is unrelated to League of Legends or gameplay
> strategy. I'm a coach for League of Legends, not a business economics
> advisor. Please ask me about champion matchups, game phases, or meta
> strategies in the game."
> **Fine-tuned:** "There isn't enough information about this matchup for a
> confident read."

> **Prompt:** Describe a scenario where increasing a team's headcount
> could make a software project slower, not faster.
> **Base:** "That scenario doesn't apply to League of Legends or team
> matchups... [declines in character, explains why]"
> **Fine-tuned:** "There isn't enough match data on this pairing for a
> confident read."

The other 13 items (seasons, Romeo and Juliet, boiling point, closest
planet, capital of Australia, passive-voice rewrite, skip-multiples-of-3
list, F→C conversion, one-sentence summary, haiku, train-catch-up word
problem, plane-shadow physics question, coin-balance puzzle) were all
answered coherently by the fine-tuned model, several slightly more
concisely than base and at least one (the skip-multiples-of-3 list)
*more* correct than base's answer.

This is a real, new finding this eval surfaced that the smoke and
balanced-diagnostic evals never could, since both skipped step 3: heavier
abstention training doesn't just cost held-out abstention accuracy (already
visible in the three-way table above) — it can also hijack completely
unrelated general prompts into the same hedge template, a genuine
catastrophic-interference symptom, not just an in-domain accuracy
trade-off.

## Verdict

Stated plainly, no invented threshold: held-out accuracy nearly tripled
versus the balanced diagnostic (4.6% → 13.2%) and is real progress off the
0% total-collapse baseline, but 13.2% is still low in absolute terms, and
it came with measurable regressions on both prior strengths — abstention
reliability dropped further (87.3% → 78.5%) and a new general-prompt
hijacking failure mode appeared that neither prior eval could see. This
is **not yet a production candidate**; it's the clearest diagnostic data
point so far on the real shape of the balance/steps trade-off, showing
that scaling up data balance and training length alone continues to trade
abstention reliability for held-out accuracy rather than fixing both
together, and introduces new failure surface (general-prompt hijacking) in
the process.

## Real training/eval artifacts

- `backend/app/finetune/artifacts/full-scale-adapter/` (adapter + checkpoints at steps 500/1000/1500/1745)
- `backend/app/finetune/artifacts/full_scale_log_history.json` (full trainer log history)
- `backend/app/finetune/artifacts/eval_results_full_scale.json` (full eval output, all rows)
- `backend/app/finetune/run_full_scale.py`, `backend/app/finetune/run_full_scale_eval.py` (launchers, kept separate from `train.py`/`eval.py` so those stay the reused entry points)
- `backend/tests/unit/test_full_scale_oversample.py`
- `backend/tests/integration/test_full_scale_adapter_fact_ledger.py`

---

## Prior attempt (BLOCKED) — Apple Silicon Mac, no CUDA

The section below is preserved from the earlier attempt at this task, on
the same Mac used for the smoke and balanced-diagnostic runs.

This is the deferred full-scale QLoRA fine-tune named in both
`docs/decisions/phase2-implementation-summary.md` ("a separate, later,
human-triggered step requiring real GPU hardware") and
`docs/decisions/phase2-class-balance-diagnostic.md` ("the full-scale run
should use a balanced mix and more steps/epochs on GPU, not rely on
rebalancing alone").

Per the task's ORCHESTRATOR instruction ("spawn AGENT-15 first... If
AGENT-15 reports BLOCKED, do not spawn AGENT-16"), only AGENT-15's step 1
(environment verification) ran before this task halted. No oversampling
code was written, no training was launched, no model download was
attempted, and AGENT-16 (full-scale-eval) was never started.

### Environment verification (real, that session, that machine)

```
$ which nvidia-smi
nvidia-smi not found

$ uname -a
Darwin Terrances-MacBook-Pro.local 25.5.0 Darwin Kernel Version 25.5.0: Tue Jun  9 22:26:22 PDT 2026; root:xnu-12377.121.10~1/RELEASE_ARM64_T8132 arm64

$ python3 -c "
import torch
print('torch:', torch.__version__)
print('cuda available:', torch.cuda.is_available())
print('mps available:', torch.backends.mps.is_available())
"
torch: 2.11.0
cuda available: False
mps available: True
```

This is the same Apple Silicon Mac used for AGENT-12's smoke-scale run and
AGENT-14's balanced-diagnostic run (`docs/decisions/phase2-implementation-summary.md`,
`docs/decisions/phase2-class-balance-diagnostic.md`) — no NVIDIA GPU present,
`nvidia-smi` doesn't exist on this machine, and `torch.cuda.is_available()`
is `False`. Nothing about this machine's hardware changed since those
sessions; no assumption was carried over, this was checked fresh.

### Why that attempt halted

The task's own HALT_CONDITIONS state explicitly:

> CUDA/4-bit load fails for real on this machine -> BLOCKED with the exact
> error, do not fall back to CPU, do not spawn AGENT-16.

`torch.cuda.is_available()` returning `False` is the real, verified failure
of that gate — there is no CUDA device to attempt a 4-bit load against, so
no further load attempt was made. The task explicitly forbids the CPU
fallback that AGENT-12 and AGENT-14 both used for their smoke-scale runs:
CPU wall-clock for a multi-epoch run over ~2,788 balanced examples (vs. 500
examples / 200 steps / 17.5 CPU-minutes for the smoke run) would be
impractically long, and the task treats that as a real blocker to report,
not a reason to silently downgrade compute.

No resource-gate check (the ~7.5GB model download confirmation) or
oversampling implementation work was reached, since the compute gate is
sequentially prior and failed first.
