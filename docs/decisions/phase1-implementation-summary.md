# Phase 1 Implementation Summary — AGENT-7 through AGENT-10

## AGENT-7 (schema-finalization) — DONE

Finalized `backend/app/models.py`: `MatchupStat` and `Advice` now key on
`(champ_a, champ_b, role, rank_bracket, phase, patch)`, with `role` added as a
first-class identity column. `Advice` gains `tier` (CHECK constraint
`tier IN ('eager','lazy')`) and `generated_at`. New `BackfillQueue`
model/table added (champ_a, champ_b, rank_bracket, phase, requested_at,
status).

Files touched:
- `backend/app/models.py`
- `backend/tests/unit/test_models.py`

**Real pytest output:**

```
============================= test session starts ==============================
platform darwin -- Python 3.12.5, pytest-9.1.1, pluggy-1.6.0 -- backend/.venv312/bin/python
rootdir: backend
collecting ... collected 6 items

tests/unit/test_models.py::test_matchup_stat_duplicate_key_raises PASSED [ 16%]
tests/unit/test_models.py::test_matchup_stat_same_pair_different_role_is_not_a_duplicate PASSED [ 33%]
tests/unit/test_models.py::test_advice_tier_rejects_value_outside_eager_lazy PASSED [ 50%]
tests/unit/test_models.py::test_advice_tier_accepts_eager_and_lazy[eager] PASSED [ 66%]
tests/unit/test_models.py::test_advice_tier_accepts_eager_and_lazy[lazy] PASSED [ 83%]
tests/unit/test_models.py::test_backfill_queue_round_trips_a_row PASSED  [100%]

============================== 6 passed in 3.05s ===============================
```

6 passed, 0 of the 5-attempt fix budget used.

---

## AGENT-8 (match-data-pipeline) — DONE

Implemented `riot_client.py` (normalized match shape + HF CSV loader) and
`aggregate.py` (filters surrendered/non-ranked matches, aggregates same-lane
matchup win rates, hardcodes `phase="not_available"` and `rank="emerald"`).

Files touched:
- `backend/app/data_pipeline/riot_client.py`
- `backend/app/data_pipeline/aggregate.py`
- `backend/tests/unit/test_aggregate.py`
- `backend/tests/integration/test_pipeline_integration.py`

**Real pytest output:**

```
$ cd backend && PYTHONPATH=. python3 -m pytest tests/unit/test_aggregate.py tests/integration/test_pipeline_integration.py -v

============================= test session starts ==============================
platform darwin -- Python 3.13.7, pytest-9.0.2, pluggy-1.6.0
collecting ... collected 13 items

tests/unit/test_aggregate.py::test_filter_valid_matches_excludes_surrenders_and_non_ranked_queue PASSED [  7%]
tests/unit/test_aggregate.py::test_aggregate_matchup_stats_hand_computed_win_rate PASSED [ 15%]
tests/unit/test_aggregate.py::test_aggregate_matchup_stats_dedupes_unordered_pair_direction PASSED [ 23%]
tests/unit/test_aggregate.py::test_no_row_ever_has_a_real_phase_bucket PASSED [ 30%]
tests/unit/test_aggregate.py::test_every_row_uses_the_fixed_emerald_rank PASSED [ 38%]
tests/unit/test_aggregate.py::test_aggregate_matchup_stats_is_idempotent PASSED [ 46%]
tests/integration/test_pipeline_integration.py::test_loader_produces_the_documented_normalized_shape PASSED [ 53%]
tests/integration/test_pipeline_integration.py::test_dataset_is_not_already_queue_filtered_verifies_the_assumption PASSED [ 61%]
tests/integration/test_pipeline_integration.py::test_filter_valid_matches_on_real_data_keeps_only_ranked_non_surrendered PASSED [ 69%]
tests/integration/test_pipeline_integration.py::test_aggregate_on_real_data_never_emits_a_real_phase_bucket PASSED [ 76%]
tests/integration/test_pipeline_integration.py::test_aggregate_on_real_data_always_uses_the_fixed_emerald_rank PASSED [ 84%]
tests/integration/test_pipeline_integration.py::test_aggregate_on_real_data_win_rates_are_valid_probabilities PASSED [ 92%]
tests/integration/test_pipeline_integration.py::test_end_to_end_pipeline_is_idempotent PASSED [100%]

=============================== warnings summary ===============================
app/config.py:11: PydanticDeprecatedSince20 (pydantic class-based Config, unrelated to this change)

======================== 13 passed, 1 warning in 0.34s ===========================
```

13 passed, 1 warning, 0 of the 5-attempt fix budget used on either component.

---

## AGENT-9 (data-dragon-ingestion) — DONE

Implemented `backend/app/data_pipeline/data_dragon.py` with
`get_current_patch()`, `fetch_champion_data(patch)`, and `_filter_variants()`
applying the name-collision variant-detection rule (dedupe by `name` field;
keep the key with no underscore prefix).

Verified live against Data Dragon before writing tests:
- `versions.json` -> current patch = `16.15.1`.
- `cdn/16.15.1/data/en_US/champion.json` -> 233 raw keys, 60 name-collision
  groups (all `Jade_*` vs base), filtered result = 173 champions, 0 ambiguous
  groups.
- Confirmed the `Jade_Wukong` edge case: its `name` is `Wukong`, which
  collides with `MonkeyKing`'s `name` (`Wukong`) even though `MonkeyKing`'s
  own key/id is not `Wukong` — name-based collision (not id/key matching) is
  required to catch it.

Files written:
- `backend/app/data_pipeline/data_dragon.py`
- `backend/tests/unit/test_data_dragon.py`

**Real pytest output:**

```
collected 5 items
tests/unit/test_data_dragon.py::test_filter_variants_drops_underscore_prefixed_duplicates PASSED [ 20%]
tests/unit/test_data_dragon.py::test_filter_variants_keeps_key_with_no_underscore_prefix PASSED [ 40%]
tests/unit/test_data_dragon.py::test_filter_variants_no_collision_passthrough PASSED [ 60%]
tests/unit/test_data_dragon.py::test_filter_variants_raises_on_ambiguous_group PASSED [ 80%]
tests/unit/test_data_dragon.py::test_live_champion_count_regression PASSED [100%]

============================== 5 passed in 0.11s ===============================
```

5 passed, 0 of the 5-attempt fix budget used.

---

## AGENT-10 (db-and-retrieval) — DONE

Implemented `backend/app/db_migrate.py` (`start_pgserver()`/`migrate()` using
`pgserver.get_server(pgdata, cleanup_mode="stop")`, then
`Base.metadata.create_all(engine)` against `app.models.Base` — matchup_stats,
advice, backfill_queue; idempotent re-run supported) and
`backend/app/retrieval/index.py` (`RetrievalIndex` wraps a local
sentence-transformers model, `all-MiniLM-L6-v2`; `champion_text()` flattens a
Data Dragon champion detail record's blurb/passive/spell text into one
string; `build()` embeds all champions; `query()` returns cosine-similarity
nearest neighbors).

Files written:
- `backend/app/db_migrate.py`
- `backend/app/retrieval/index.py`
- `backend/tests/integration/test_db_migrate.py`
- `backend/tests/integration/test_retrieval_index.py`

**Real pytest output:**

```
$ python3 -m pytest tests/integration/test_db_migrate.py tests/integration/test_retrieval_index.py -v
tests/integration/test_db_migrate.py::test_all_expected_tables_exist PASSED [ 11%]
tests/integration/test_db_migrate.py::test_table_has_expected_columns[advice] PASSED [ 22%]
tests/integration/test_db_migrate.py::test_table_has_expected_columns[backfill_queue] PASSED [ 33%]
tests/integration/test_db_migrate.py::test_table_has_expected_columns[matchup_stats] PASSED [ 44%]
tests/integration/test_db_migrate.py::test_advice_tier_check_constraint_rejects_invalid_value PASSED [ 55%]
tests/integration/test_db_migrate.py::test_migrate_is_idempotent_rerun PASSED [ 66%]
tests/integration/test_retrieval_index.py::test_champion_text_includes_real_ability_text PASSED [ 77%]
tests/integration/test_retrieval_index.py::test_nearest_neighbor_is_the_correct_champion PASSED [ 88%]
tests/integration/test_retrieval_index.py::test_unrelated_query_does_not_match_ashe PASSED [100%]
9 passed in 6.84s
```

9 passed, 0 fix-attempt iterations needed for either component.

Full backend suite (this agent's 2 new files plus pre-existing tests from
other agents) also run to confirm no regressions:
`python3 -m pytest -q` -> "33 passed, 1 warning in 8.69s".
