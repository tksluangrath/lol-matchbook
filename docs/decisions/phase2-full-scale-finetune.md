# Phase 2 Full-Scale Fine-Tune — AGENT-15/AGENT-16

**Status: BLOCKED.**

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

## Environment verification (real, this session, this machine)

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

## Why this halts the task

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

## What did NOT happen (explicitly, per contract)

- `oversample_to_balance` was not implemented; `backend/tests/unit/test_full_scale_oversample.py` was not written.
- No training was launched; `backend/app/finetune/artifacts/full-scale-adapter/` does not exist.
- No batch-size or epoch-count benchmarking occurred.
- AGENT-16 (full-scale-eval) was not spawned; `eval_results_full_scale.json` does not exist.
- `phase2-implementation-summary.md` and `phase2-class-balance-diagnostic.md` were not modified, per the completion instructions for this task.

## Next step

This needs real GPU hardware this machine does not have — a cloud GPU
instance or a different machine with a working CUDA install. Re-run
AGENT-15 there; its step 1 environment verification should be repeated
fresh on whatever hardware is used, not assumed from this doc.
