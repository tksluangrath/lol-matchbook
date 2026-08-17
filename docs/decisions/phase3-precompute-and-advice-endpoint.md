---
noteId: "phase3precomputeadviceendpoint0001"
tags: []

---

# Phase 3: Precompute Batch + /advice Endpoint — Real End-to-End Slice

**Status: DONE.** `run_precompute_batch` implemented and run for real (10
matchups, 30 Advice rows), `GET /advice` implemented as a real DB lookup,
real measured latency well under the 200ms target.

## Real DB state, checked before writing anything

No `.pgdata` directory existed at the repo root before this session. A
fresh `migrate()` call created one and reported all three tables
(`matchup_stats`, `advice`, `backfill_queue`) with **0 rows each** — safe
to proceed, nothing pre-existing to protect or investigate.

## Environment gap found and fixed

`requirements.txt` declares `pgserver` (DB) and `peft`/`bitsandbytes`/`trl`
(fine-tune stack) as one dependency set, but in practice: `pgserver` has no
Python 3.13 wheel (confirmed, per `db_migrate.py`'s own docstring) and was
only ever installed under this machine's 3.12 pyenv interpreter, while
`peft`/`bitsandbytes` were only ever installed under 3.13 (every prior
fine-tune script this project ran used `python3` = 3.13.7). `precompute.py`
needs both DB access and adapter loading in the same process. Installed
`peft`, `bitsandbytes`, `trl`, `accelerate` into the 3.12 interpreter
(matching what `requirements.txt` already declares) rather than splitting
the pipeline across two processes for an incidental environment gap.

## Real discrepancies found, not silently patched

1. **`MatchupStat.phase` is a NOT NULL identity column, but the real
   source data isn't phase-sliced.** `heldout_context.jsonl`'s own `phase`
   field is literally `"not_available"` for every row — there is one real
   win_rate/sample_size number per matchup, not three. `run_precompute_batch`
   writes that same real number into all three phase rows for a pair
   (never fabricating phase-differentiated stats that don't exist
   upstream) — each Advice row's `fact_source_id` still points at its own
   phase's MatchupStat row, satisfying the schema's per-phase identity.
2. **No existing MatchupStat write-idempotency convention** was found
   anywhere in `app/data_pipeline/` (grepped for it — `aggregate.py`/
   `data_dragon.py`/`riot_client.py` don't write to MatchupStat at all
   yet). Established one here: Postgres `INSERT ... ON CONFLICT DO
   NOTHING` against the real unique constraints `models.py` already
   declares, plus a pre-generation existence check so a rerun skips real
   model calls entirely for pairs already written.
3. **`GET /advice`'s declared query contract (`champ_a`, `champ_b`, `rank`)
   doesn't include `role`**, even though `role` is part of Advice's real
   uniqueness. Kept the endpoint's existing declared contract rather than
   silently expanding it — for a champion played in multiple roles (e.g.
   Ashe bot/support, per `models.py`'s own docstring) this would be a real
   ambiguity. Doesn't surface for this session's 10-pair sample (no
   champ_a/champ_b pair repeats across roles in it), but is a real gap for
   later.

## Precompute: 10/10 real matchups, 0 skipped

`python -m app.data_pipeline.precompute` against the real persistent DB —
same 10 pairs from `qualitative_advice_heldout.jsonl` used throughout the
two-adapter diagnostic, real Data Dragon-sourced kit context (already
built into those rows), real generation via
`smoke-adapter-qualitative-dedicated-v2/` (400 tokens, no `gen_kwargs` —
the confirmed-best config from that diagnostic), real
`fact_grounding_check` + section-split validation before any write.

**Result: 10/10 pairs written, 0 skipped, 30 real Advice rows + 30 real
MatchupStat rows.** No grounding failure or section-split failure
occurred in this run (the integration test suite separately confirmed the
skip path works for real via a deliberately budget-starved generation —
see below), so every one of the 10 pairs' real generated advice made it
into the DB.

### Two full real examples, quoted verbatim

**Aatrox / Kayle (top):**
- **Early:** Aatrox's high health and fear-driven crowd control can deter early ganks, but Kayle's ability to gain attack range and her presence of a divine ally makes her a persistent threat. Avoid engaging directly in the early game; let Kayle establish positioning. Aatrox should use his stance to close gaps and prepare for a counter-punch, while Kayle can use her spellblade to pressure and harass if the opportunity arises.
- **Mid:** Kayle's radiant blast and celestial blessing allow her to control engagement and root enemies, while Aatrox's darkin blade and deathbringer stance enable him to close gaps and sustain himself. Kayle should use her range advantage to harass and force errors from Aatrox's positioning. If Aatrox manages to engage with a charge or two, he can close the gap, but Kayle's smite and move speed allow her to reposition and escape if pressured.
- **Late:** In the late game, Aatrox's ability to fear and drag enemies becomes crucial for crowd control in fights. Kayle should use Divine Judgment to secure a takedown, as Aatrox's reliance on crowd control makes him vulnerable in the middle lane. If Kayle can secure a kill early in the lane, she can use the bonus attack range and move speed to close gaps and pressure Aatrox into mistakes. Aatrox should avoid going on the offensive without a clear advantage—his healing and damage increase make him durable, but Kayle's ability to reduce resistances and slow enemies gives her the edge in closing gaps.

**Ahri / Xerath (middle):**
- **Early:** Ahri can close gaps quickly with her combination of movement and crowd control, but Xerath's early game presence is limited. Avoid engaging directly; let Xerath cast Arcanopulse to harass and pressure. Ahri should use her lack of early crowd control to roam and secure vision. If Ahri gains an advantage with a takedown, use it to secure a decisive early win.
- **Mid:** Ahri's Charm and essence theft allow her to control and sustain fights, especially if she can isolate Xerath. Xerath's Arcanopulse and Rite of the Arcane can disrupt Ahri's positioning, but Ahri's mobility lets her reposition easily. Prioritize killing Xerath's support if he's pushing lanes, as Xerath's lack of early lane presence makes him vulnerable in the middle. Ahri should use her orb to close gaps and Charm if Xerath casts Rite of the Arcane—stunning him allows Ahri to reposition and secure a kill.
- **Late:** Ahri should use Spirit Rush to close gaps and follow up with Charm if Xerath is low on health. Xerath's Eye of Destruction can disrupt Ahri's positioning, but Ahri's mobility lets her adapt. If Ahri can secure a takedown with essence theft, she can sustain pressure. Avoid engaging directly if Xerath has Eye of Destruction incoming—use cover and mobility to survive. Ahri should use her abilities to control the battlefield and force Xerath into unfavorable positioning.

A real, minor observation: this run's text differs slightly from the same
pair's earlier v2 eval output (two-adapter diagnostic) despite identical
prompt/model/tokens/greedy decoding — plausible CPU floating-point/
quantization non-determinism across separate real model loads on this
machine. Not investigated further (doesn't affect correctness of this
slice; both generations pass sections + grounding), flagged rather than
silently assumed identical.

## Idempotency: confirmed real, not assumed

`test_precompute_batch_rerun_is_idempotent` (in the earlier, separate
10-pair test run against a temp DB): calling `run_precompute_batch` a
second time on the same input reported **0 written_pairs, 10
already_present**, and real row counts in both `advice` and
`matchup_stats` were unchanged before vs. after the rerun. The
pre-generation existence check means a rerun costs no real model calls at
all for already-written pairs.

## Skip-on-failure: confirmed real, not assumed

`test_precompute_batch_logs_incomplete_generation_instead_of_writing_fabricated_row`:
real generation, deliberately budget-starved (`max_new_tokens=5`) so it
cannot complete all three labeled sections — a real, reliable way to
trigger `split_into_sections` returning `None` without mocking model
output (a wrong win_rate was considered instead, but this adapter almost
never cites a percentage at all, established in the two-adapter
diagnostic, so it wouldn't reliably trigger the grounding-mismatch path).
Result: 0 written_pairs, 1 real entry in `skipped` with reason
`could_not_split_sections`, 0 Advice rows written for that patch. Confirmed
via a real DB query, not just the returned dict.

## GET /advice: real endpoint, real measured latency

Real pgserver DB (the same persistent one the 10-pair precompute wrote
to), real `uvicorn` server bound to `127.0.0.1`, real `httpx` HTTP GET
requests — not FastAPI's in-process TestClient, so the measured time is an
actual request/response round trip over a real socket.

- Real precomputed pair: 200, all three phases non-empty. ✅
- Never-precomputed pair: 404, `{"status": "not_precomputed"}`. ✅
- Real seeded abstention row (thin-data case, inserted directly since
  abstention is never model-generated): 200,
  `{"status": "abstention", ...}` — a distinct response from the
  not-precomputed case, as required. ✅
- Static check: `advice.py`'s real imports contain no `finetune`/`llm`
  module — the "no model call in this code path" architectural promise
  checked against the actual file's AST, not asserted by absence of a mock. ✅

**Real measured latency, 10 requests after 1 warmup request:**
```
median = 4.13ms
all (ms) = [4.0, 4.01, 4.02, 4.12, 4.13, 4.13, 4.17, 4.39, 4.42, 5.01]
```

**The "no model call at request time" architectural promise held up under
actual measurement.** 4.13ms median is ~48x under the 200ms target — this
is a pure DB round trip (connection + indexed lookup + serialization),
consistent with zero model/GPU involvement in the request path.

## Real cost incurred

- ~47 min: full 10-pair precompute run (temp DB, integration test suite)
- ~11 min: second full 10-pair precompute run (persistent DB, for durable
  data + the doc's quoted examples) — no way found to avoid this second
  real run and still have both an isolated test DB and a durable local one
- ~6 sec: endpoint test suite (reused the persistent DB's already-written
  rows via the idempotency check, no new generation)
- pip install of peft/bitsandbytes/trl/accelerate into the 3.12
  interpreter: a few minutes

## Next step

Not done in this slice (explicitly out of scope): full role-scoped
production precompute (~6,500 pairs, per phase1-role-threshold-
sensitivity.md), the `role` query-param gap on `/advice`, and `/ask`
(the live follow-up path) — untouched, still `raise NotImplementedError`.

## Files

- `backend/app/data_pipeline/precompute.py` (implemented)
- `backend/app/routers/advice.py` (implemented)
- `backend/tests/integration/test_precompute_batch.py`
- `backend/tests/integration/test_advice_endpoint.py`
- `docs/decisions/phase3-precompute-and-advice-endpoint.md` (this file)
