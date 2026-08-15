---
noteId: "e7738f20982811f1af4f3319e0cf7c04"
tags: []

---

# Phase 2 Qualitative Extended-Steps Diagnostic — AGENT-24

**Status: BLOCKED (killed by user after real duration divergence).**

Tests whether extending the step budget to a full 2 epochs (700 steps over
the same 700-row, 28.6%-qualitative mix used in
`docs/decisions/phase2-qualitative-oversampling-diagnostic.md`) fixes the
qualitative-advice task's complete failure, isolating step budget as the
one variable not yet tested.

## Mix reconstruction — verified identical to the prior run

```
$ git pull
Already up to date.

qual rows: 40
win_rate_sample: 500
qual_oversampled total: 200
unique qual rows in oversampled: 40
all appear exactly 5x: True
total combined: 700
```
Matches the prior diagnostic's reported composition exactly (500 win-rate +
200 qualitative, every one of the 40 real rows appearing exactly 5 times,
zero remainder). Confirmed before training, per the task contract.

## Training run — real duration diverged massively from the ~2h projection

Stated the projection (~2h, based on the prior 200-step run's real 33
minutes) before starting; user confirmed to proceed.

Real progress, live tqdm (SFTTrainer's default progress bar; per-step
`{'loss': ...}` log lines that appeared in every prior run's log did not
appear in this run's captured output — training was still real and
progressing per the live step counter and process CPU usage, just without
that particular console line this session; not investigated further since
the run was killed before completion):

```
$ ps -p 86866 -o pid,etime,command
86866 06:53:26 ...run_qualitative_extended_training.py
```
**6h53m real elapsed, step 468/700 (66.9%)** — nearly 3.5x the ~2h
projection.

Root cause of the divergence, quantified from the real tqdm timestamps: one
single step (266→267) stalled for **22,342 real seconds (6h12m)** — the
entire divergence is essentially this one stall. Aside from it, per-step
speed was normal and fairly stable (~8-16s/step), close to the prior run's
observed rate. Several smaller stalls (15-45 min each) also occurred around
steps 115-135 and 244-245:

```
22342s between step 266 and 267
2777s between step 120 and 121
1991s between step 116 and 117
1535s between step 115 and 116
1189s between step 244 and 245
1112s between step 130 and 131
1077s between step 135 and 136
1047s between step 123 and 124
1018s between step 134 and 135
836s between step 118 and 119
```

This is the same category of intermittent, unexplained multi-hour
single-step slowdown documented on the Windows/GPU full-scale run
(`docs/decisions/phase2-full-scale-finetune.md`), now observed on this
Apple Silicon CPU-only machine for the first time. No confirmed root cause
here (unlike the GPU run's shared-VRAM-fallback diagnosis) — plausible
contributors not verified: thermal throttling, memory pressure from mixing
long qualitative sequences with short win-rate ones in the same shuffled
batch stream, or unrelated system load. Flagged as a real, unresolved
finding, not glossed over.

## Outcome

Per the task's own halt condition ("training duration diverges
substantially from the ~2-hour projection once running -> say so rather
than letting it run unbounded"), the divergence was reported to the user in
real time once confirmed (step 468/700, 6h53m elapsed, the 6h12m single-step
stall identified). The user chose to kill the process rather than let it
finish the remaining ~230 steps.

**No adapter was saved** (`smoke-adapter-qualitative-extended/` is empty —
`trainer.save_model()` is only reached after `trainer.train()` returns, and
the process was killed first). No fact_ledger check, no qualitative eval,
no win-rate regression check were run — there is no trained artifact to
evaluate.

**This diagnostic did not test its hypothesis.** Whether 2 full epochs at
28.6% qualitative share would fix the qualitative-advice task remains
unanswered — the run got to 66.9% of its step budget with normal per-step
performance throughout (excluding the anomalous stalls), so nothing here
contradicts the hypothesis either; it simply wasn't allowed to finish.

## Real cost incurred

~6h53m of real CPU time consumed with no usable artifact — worth weighing
against the two-adapter/two-stage alternative both prior diagnostics named,
which doesn't carry this same multi-hour single-step-stall risk profile
(smaller, more homogeneous per-task training runs are less exposed to
whatever caused this stall, if it's related to long-sequence memory
pressure in the mixed batch stream).

## Next step

Re-attempt only with either: (a) a resumable checkpoint strategy
(`save_steps` set so a stall-then-kill doesn't lose all progress), or
(b) move directly to the two-adapter/two-stage approach, which was already
the recommended fallback in `docs/decisions/phase2-qualitative-oversampling-diagnostic.md`
before this run even started.

## Files

- `docs/decisions/phase2-qualitative-extended-steps-diagnostic.md` (this file)
- No adapter, no eval results, no new test file — none of AGENT-24's other
  planned outputs were reached before the halt.
