---
noteId: "phase4askqualityfix0001"
tags: []

---

# Phase 4: Fixing /ask's Output Quality — Real Root Cause, Real Before/After

**Status: DONE.** Root cause confirmed by reading the actual code, not
guessed: a retrieval-scope gap plus a prompt-shape mismatch, not an
adapter capability problem. Fixed both; real regenerated answer verified
against the real backend.

## The real sample that motivated this

Real question, "How do I win the late game?", Aatrox vs Kayle, before this
fix — a flat list of ability-tooltip restatements, no win condition, no
direct answer to the question asked. The same adapter's precompute-path
output for the same matchup, same phase (`docs/decisions/
phase3-precompute-and-advice-endpoint.md`) is markedly better: *"Kayle
should use Divine Judgment to secure a takedown, as Aatrox's reliance on
crowd control makes him vulnerable."* — a stated win condition, not a kit
summary. Same model, same pair, same phase — different quality. That
ruled out "the adapter can't do this."

## Real root cause #1: /ask never queried the Advice table

`app/llm/context.py`'s `build_ask_context()` queried `MatchupStat` for the
win-rate sentence, and fetched raw Data Dragon kit text — but never
queried `Advice` at all. The already-generated, already-fact-checked
early/mid/late text for this exact pair (the good output quoted above)
was completely absent from `/ask`'s context. The model was being asked to
re-derive strategy from raw ability blurbs alone, with none of the
already-done causal reasoning available to build on.

## Real root cause #2: the instruction line was an out-of-distribution prompt shape

`/ask`'s instruction asked the model to "answer the user's question...
specifically and concisely" — a shape the adapter was never fine-tuned on.
Every real training example (`app/finetune/qualitative_advice.py`'s
`build_generation_prompt()`) used a fixed instruction: "write strategic
{role}-lane matchup advice in exactly three labeled sections." Asking a
narrowly fine-tuned adapter to follow a novel instruction shape is a real,
known way to get shallower, less-causal output — consistent with what was
observed.

Neither root cause required retraining or re-tuning the adapter — both
are retrieval/prompt-layer fixes, confirmed by the adapter's own good
output on the familiar shape.

## The fix

`app/llm/context.py`:
- `_lookup_precomputed_advice()` (new): real DB query for existing
  early/mid/late Advice text for the pair, same exact-match-then-
  wider-rank-bracket-fallback pattern `_stats_block()` already used.
  Excludes abstention rows (no real advice text to ground on). Included
  in the prompt as a labeled "Precomputed strategic notes" block when
  found; omitted entirely (not fabricated) when nothing exists.
- Instruction rewritten to ask for the same win-condition-first, causally-
  reasoned register the adapter actually learned, redirected at the live
  question: state the win condition in the first sentence or two, then key
  levers (not an ability-by-ability list), then directly answer the
  question.
- `build_ask_context()` now returns an `AskContext(prompt,
  grounding_source, win_rate_pct)` instead of a plain string — a real,
  deliberate contract change, needed so the caller can run a real
  grounding check.

`app/routers/ask.py`:
- Accumulates the full streamed response server-side, then runs the real,
  unmodified `fact_grounding_check()` (the same check
  `precompute.py`'s pipeline already gates writes on) against
  `grounding_source` and `win_rate_pct`. `/ask` streams live and can't
  regenerate on failure without real added latency the way `precompute.py`
  can, so a failed check sends `{"type": "warning", "message": ...}`
  before `"done"` — the already-streamed answer is flagged, not silently
  dropped or silently shipped as if verified.

`frontend/src/api/ask.ts`: handles the new `warning` message type as
non-fatal (yields it as a visible, distinguishable chunk rather than
throwing and aborting the stream, which the pre-fix client would have done
for any message type it didn't recognize as `chunk`/`done`).

## Real before/after (Aatrox vs Kayle, top, emerald, "How do I win the late game?")

**Before** (quoted in this task's brief): a flat list of ability-tooltip
restatements, no win condition stated, no direct answer.

**After**, real regenerated response against the real local backend, no
grounding warning triggered:

> Kayle should win the late game by using Divine Judgment to secure
> takedowns and exploiting Aatrox's reliance on crowd control. In the
> final stages, Aatrox's fear and drag abilities become predictable, and
> Kayle's celestial sword's damage scaling against missing health allows
> her to close gaps and pressure him into mistakes. Prioritize securing
> kills early to gain attack range and move speed, then use Radiant Blast
> to root and slow enemies while Celestial Blessing supports your ally.
> Avoid direct confrontation without a clear advantage — Aatrox's healing
> and damage increase make him durable, but Kayle's ability to reduce
> resistances and slow enemies gives her the edge in fights.

Win condition stated in sentence one. Organized (win condition → key
levers → caution), not an ability-by-ability list. Directly answers the
question asked. All named abilities (Divine Judgment, Radiant Blast,
Celestial Blessing) are real Kayle abilities — confirmed by the real
grounding check running clean, not by inspection alone.

## Real regression check

`tests/unit/test_ask_context_builder.py` (7 tests, including new coverage
for precomputed-advice retrieval, abstention exclusion, and the
win-condition instruction), `tests/integration/test_ask_endpoint.py` (2),
`tests/integration/test_advice_endpoint.py` (6), `tests/integration/
test_lazy_tier_fallback.py` (3) — 18/18 pass. Frontend: 39/39 tests pass,
clean build.

## Next step

Not done here: no automated test asserts a grounding *failure* actually
produces a visible warning end-to-end (the real question tested happened
to pass grounding cleanly) — the unit-level `fact_grounding_check` reuse
is proven, and the warning-message plumbing is code-reviewed but not
exercised by a real failing case in CI. Worth a follow-up test that seeds
a prompt likely to produce an ungrounded claim, if this needs stronger
coverage later.
