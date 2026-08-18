"""
Offline batch job (Phase 3): generates real early/mid/late advice for a
small, deterministic sample of matchups via the dedicated qualitative
adapter and writes MatchupStat + Advice rows.

Only one model is invoked: backend/app/finetune/artifacts/
smoke-adapter-qualitative-dedicated-v2/ (the two-adapter diagnostic's
10/10 adapter). The numeric win-rate task does not get its own model call
here -- docs/decisions/phase2-context-conditioning-diagnostic.md proved the
model faithfully restates given context, so real win_rate/sample_size
numbers are formatted into the same context-block string
qa_generation.py's build_context_conditioned_row validated ("Context: N
games observed this patch between A and B in the R lane. A win rate: W%.")
and fed into the qualitative adapter's prompt as input.

Sample scope: the same 10 pairs from qualitative_advice_heldout.jsonl used
throughout the two-adapter diagnostic -- already carry real, validated kit
context (win-rate block + both champions' real Data Dragon kit text). Full
role-scoped production scale (~6,500 pairs) is out of scope for this slice;
this validates the real pipeline end-to-end first.

Real discrepancy found, not papered over: MatchupStat.phase is a NOT NULL
identity column, but the real match-data this session's rows trace back to
is not phase-sliced -- heldout_context.jsonl's own phase field is literally
"not_available" for every row; there is one real win_rate/sample_size
number per matchup, not three. This job writes that same real number into
all three phase rows for a pair (rather than fabricating phase-
differentiated stats that don't exist upstream) -- each Advice row's
fact_source_id points at its own phase's MatchupStat row, satisfying the
schema's per-phase identity without inventing per-phase numbers.

Also: no existing MatchupStat write-idempotency convention was found
anywhere in app/data_pipeline/ (grepped for it -- aggregate.py/
data_dragon.py/riot_client.py don't write to MatchupStat at all yet), so
this establishes one: Postgres INSERT ... ON CONFLICT DO NOTHING against
the real unique constraints models.py already declares.
"""
import json
import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.data_pipeline.aggregate import aggregate_matchup_stats, filter_valid_matches
from app.data_pipeline.riot_client import load_hf_csv_matches
from app.finetune.eval import generate, load_model_and_tokenizer
from app.finetune.qualitative_advice import (
    ability_whitelist_block,
    champion_text,
    fact_grounding_check,
    fetch_champion_detail,
)
from app.models import Advice, MatchupStat

DATA_DIR = Path(__file__).resolve().parents[1] / "finetune" / "data"
QUAL_HELDOUT_PATH = DATA_DIR / "qualitative_advice_heldout.jsonl"
HELDOUT_CONTEXT_PATH = DATA_DIR / "heldout_context.jsonl"
DEFAULT_ADAPTER_DIR = (
    Path(__file__).resolve().parents[1] / "finetune" / "artifacts" / "smoke-adapter-qualitative-dedicated-v2"
)
MAX_NEW_TOKENS = 400

# Real cached HF dataset CSV path -- same source phase1-role-pair-count.md
# and every prior real aggregation run this project used, not re-downloaded.
DEFAULT_MATCH_CSV = (
    "/Users/terrance/.cache/huggingface/hub/datasets--BoostedJonP--league_of_legends_match_data/"
    "snapshots/00aa8cff89383127ff6a2d7d26a6b01fcef80c04/league_of_legends_emerald_match_data.csv"
)

CONTEXT_RE = re.compile(r"Context: (\d+) games? observed this patch between .+ win rate: (\d+)%")

# Same broadened label matching validated in the two-adapter diagnostic
# (run_qualitative_dedicated_eval.py) -- real held-out generations use
# label variants ("Mid-game:", "Late game:") with full, real content under
# them; a stricter exact-match splitter would silently drop real advice.
EARLY_RE = re.compile(r"\bEarly:")
MID_RE = re.compile(r"\bMid-?game:|\bMid:")
LATE_RE = re.compile(r"\bLate\s*game:|\bLate:")


def load_sample_pairs(n: int = 10) -> list[dict]:
    """The n pairs from qualitative_advice_heldout.jsonl (real kit context,
    already validated), joined with heldout_context.jsonl for rank_bracket
    and the real win_rate/sample_size numbers (re-extracted from that row's
    own context-block text via CONTEXT_RE -- the same real numbers qa_
    generation.py originally formatted in, not re-derived from a different
    source)."""
    qual_rows = [json.loads(l) for l in QUAL_HELDOUT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()][:n]
    ctx_rows = {
        (r["champ_a"], r["champ_b"], r["role"]): r
        for r in (json.loads(l) for l in HELDOUT_CONTEXT_PATH.read_text(encoding="utf-8").splitlines() if l.strip())
    }

    pairs = []
    for row in qual_rows:
        key = (row["champ_a"], row["champ_b"], row["role"])
        ctx_row = ctx_rows[key]
        m = CONTEXT_RE.search(ctx_row["prompt"])
        if not m:
            raise ValueError(f"could not parse real sample_size/win_rate from {key}'s context: {ctx_row['prompt']!r}")
        sample_size, win_rate_pct = int(m.group(1)), int(m.group(2))
        pairs.append({
            "champ_a": row["champ_a"], "champ_b": row["champ_b"], "role": row["role"],
            "rank_bracket": ctx_row["rank"], "sample_size": sample_size,
            "win_rate": win_rate_pct / 100, "generation_prompt": row["context"],
        })
    return pairs


def rank_real_candidate_pairs(csv_path: str = DEFAULT_MATCH_CSV) -> list[dict]:
    """Runs the real aggregation pipeline (app.data_pipeline.riot_client +
    aggregate, unmodified) against the real cached match CSV and returns
    every real (champ_a, champ_b, role) row with real match data behind it,
    sorted by sample_size (observed game count, a play-volume proxy)
    descending. This is the real, data-backed candidate pool -- not the
    6,512 theoretical same-lane-role-pairing ceiling, which counts pairs
    that are *allowed* to exist, not ones anyone actually played."""
    matches = load_hf_csv_matches(csv_path)
    valid = filter_valid_matches(matches)
    rows = aggregate_matchup_stats(valid)
    rows.sort(key=lambda r: r["sample_size"], reverse=True)
    return rows


def build_pair_with_context(stat_row: dict) -> dict:
    """Fetches real Data Dragon kit text for both champions (2 real
    requests) and builds the same generation_prompt shape
    run_precompute_batch expects, from a real aggregate_matchup_stats row.
    Real network calls -- only call this for pairs actually selected for
    precompute, not the whole candidate pool."""
    champ_a_detail = fetch_champion_detail(stat_row["champ_a"])
    champ_b_detail = fetch_champion_detail(stat_row["champ_b"])
    game_word = "game" if stat_row["sample_size"] == 1 else "games"
    win_rate_pct = round(stat_row["win_rate"] * 100)
    context_block = (
        f"Context: {stat_row['sample_size']} {game_word} observed this patch between "
        f"{stat_row['champ_a']} and {stat_row['champ_b']} in the {stat_row['role']} lane. "
        f"{stat_row['champ_a']} win rate: {win_rate_pct}%."
    )
    champ_a_kit = f"{stat_row['champ_a']} kit: {champion_text(champ_a_detail)}"
    champ_b_kit = f"{stat_row['champ_b']} kit: {champion_text(champ_b_detail)}"
    whitelist = ability_whitelist_block(stat_row["champ_a"], champ_a_detail, stat_row["champ_b"], champ_b_detail)
    return {
        "champ_a": stat_row["champ_a"], "champ_b": stat_row["champ_b"], "role": stat_row["role"],
        "rank_bracket": stat_row["rank"], "sample_size": stat_row["sample_size"],
        "win_rate": stat_row["win_rate"],
        "generation_prompt": f"{context_block}\n{champ_a_kit}\n{champ_b_kit}\n{whitelist}",
    }


def split_into_sections(text: str) -> dict[str, str] | None:
    """Splits real generated text into {"early": ..., "mid": ..., "late":
    ...} using the first match of each label regex, sliced between
    consecutive label positions. Returns None if any of the three labels is
    missing -- caller must not write a fabricated section for a label that
    was never generated."""
    found = []
    for phase, regex in (("early", EARLY_RE), ("mid", MID_RE), ("late", LATE_RE)):
        m = regex.search(text)
        if m:
            found.append((m.start(), m.end(), phase))
    if len(found) != 3:
        return None
    found.sort()
    sections = {}
    for i, (start, end, phase) in enumerate(found):
        content_end = found[i + 1][0] if i + 1 < len(found) else len(text)
        sections[phase] = text[end:content_end].strip()
    return sections


def _advice_already_written(session: Session, pair: dict, patch: str) -> bool:
    existing = session.execute(
        select(Advice.id).where(
            Advice.champ_a == pair["champ_a"], Advice.champ_b == pair["champ_b"],
            Advice.role == pair["role"], Advice.rank_bracket == pair["rank_bracket"],
            Advice.patch == patch,
        )
    ).first()
    return existing is not None


def _generate_and_check_pair(pair: dict, model, tokenizer, max_new_tokens: int, **gen_kwargs) -> dict:
    """Real generate() call for one pair + grounding/section-split check.
    No DB access -- callers decide what (if anything) to do to existing
    rows based on whether this passed, before writing anything.
    `**gen_kwargs` passes through to eval.generate() unchanged (empty by
    default -> the existing greedy/deterministic behavior); used by
    _generate_and_check_pair_with_sampling_retry to override decoding on
    retry attempts only."""
    output = generate(model, tokenizer, pair["generation_prompt"], max_new_tokens, **gen_kwargs)
    expected_pct = round(pair["win_rate"] * 100)
    grounding = fact_grounding_check(output, pair["generation_prompt"], expected_pct)
    sections = split_into_sections(output)

    if sections is None or not grounding["passed"]:
        return {
            "passed": False,
            "champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"],
            "reason": "could_not_split_sections" if sections is None else "grounding_failed",
            "invented_phrases": grounding["invented_phrases"],
            "model_output": output,
        }
    return {"passed": True, "sections": sections}


# docs/decisions/phase3-ability-whitelist-retry.md's root-cause finding:
# generation here is greedy/deterministic (eval.generate's do_sample=False
# default), so a single failing attempt never self-corrects. temperature=0.7/
# top_p=0.9 are the standard "mild" sampling defaults (same range
# Hugging Face's own generate() docs use as an example) -- not tuned per
# pair, just enough randomness to let the model land on a different token
# path than the deterministic one that already failed.
SAMPLING_GEN_KWARGS = {"do_sample": True, "temperature": 0.7, "top_p": 0.9}
MAX_SAMPLING_RETRIES = 2  # extra attempts after the initial greedy one


def _generate_and_check_pair_with_sampling_retry(pair: dict, model, tokenizer, max_new_tokens: int) -> dict:
    """Same contract as _generate_and_check_pair (one greedy attempt), but
    falls back to up to MAX_SAMPLING_RETRIES sampled attempts
    (SAMPLING_GEN_KWARGS) if the greedy attempt fails grounding/section-
    split. Returns the first attempt (greedy or sampled) that passes; if
    all attempts fail, returns the LAST attempt's failing result unchanged
    -- same skip-reason shape callers already handle, no new failure mode."""
    check = _generate_and_check_pair(pair, model, tokenizer, max_new_tokens)
    if check["passed"]:
        return check
    for _ in range(MAX_SAMPLING_RETRIES):
        check = _generate_and_check_pair(pair, model, tokenizer, max_new_tokens, **SAMPLING_GEN_KWARGS)
        if check["passed"]:
            return check
    return check


def _write_pair_sections(session: Session, pair: dict, patch: str, sections: dict[str, str]) -> dict:
    """Writes MatchupStat rows (ON CONFLICT DO NOTHING) + Advice rows for
    `pair`, given sections that already passed _generate_and_check_pair.
    Shared by run_precompute_batch and force_regenerate_pairs so the two
    never drift -- one real write path, not two."""
    phase_to_stat_id = {}
    for phase in ("early", "mid", "late"):
        stmt = insert(MatchupStat).values(
            champ_a=pair["champ_a"], champ_b=pair["champ_b"], role=pair["role"],
            rank_bracket=pair["rank_bracket"], phase=phase,
            win_rate=pair["win_rate"], sample_size=pair["sample_size"], patch=patch,
        ).on_conflict_do_nothing(
            index_elements=["champ_a", "champ_b", "role", "rank_bracket", "phase", "patch"]
        ).returning(MatchupStat.id)
        result = session.execute(stmt).first()
        if result is None:
            result = session.execute(
                select(MatchupStat.id).where(
                    MatchupStat.champ_a == pair["champ_a"], MatchupStat.champ_b == pair["champ_b"],
                    MatchupStat.role == pair["role"], MatchupStat.rank_bracket == pair["rank_bracket"],
                    MatchupStat.phase == phase, MatchupStat.patch == patch,
                )
            ).first()
        phase_to_stat_id[phase] = result[0]

    for phase in ("early", "mid", "late"):
        session.execute(
            insert(Advice).values(
                champ_a=pair["champ_a"], champ_b=pair["champ_b"], role=pair["role"],
                rank_bracket=pair["rank_bracket"], phase=phase, text=sections[phase],
                fact_source_id=phase_to_stat_id[phase], patch=patch,
                is_abstention=0, tier="eager",
            ).on_conflict_do_nothing(
                index_elements=["champ_a", "champ_b", "role", "rank_bracket", "phase", "patch"]
            )
        )
    session.commit()
    return {"champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"]}


def run_precompute_batch(patch: str, engine=None, pairs: list[dict] | None = None,
                          adapter_dir: Path = DEFAULT_ADAPTER_DIR, max_new_tokens: int = MAX_NEW_TOKENS) -> dict:
    """Generates real advice for `pairs` (defaults to the 10-pair sample)
    via the dedicated qualitative adapter and writes MatchupStat + Advice
    rows to `engine`. Idempotent: a pair whose Advice rows already exist
    for this patch is skipped before generation (no wasted model call, no
    duplicate rows -- ON CONFLICT DO NOTHING on the write itself is the
    second, belt-and-suspenders layer). A pair whose generation fails
    fact-grounding or can't be split into three real sections is logged in
    the returned dict's "skipped" list, never written as a fabricated row.
    """
    if pairs is None:
        pairs = load_sample_pairs()

    session = sessionmaker(bind=engine)()

    written_pairs, skipped, already_present = [], [], []
    model = tokenizer = None
    try:
        for pair in pairs:
            if _advice_already_written(session, pair, patch):
                already_present.append({"champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"]})
                continue

            if model is None:
                model, tokenizer = load_model_and_tokenizer(adapter_dir)

            check = _generate_and_check_pair(pair, model, tokenizer, max_new_tokens)
            if not check["passed"]:
                skipped.append(check)
                continue
            written_pairs.append(_write_pair_sections(session, pair, patch, check["sections"]))
    finally:
        session.close()

    return {"written_pairs": written_pairs, "already_present": already_present, "skipped": skipped}


def force_regenerate_pairs(patch: str, targets: list[tuple[str, str, str]], engine=None,
                            pairs: list[dict] | None = None, adapter_dir: Path = DEFAULT_ADAPTER_DIR,
                            max_new_tokens: int = MAX_NEW_TOKENS, sampling_retry: bool = False) -> dict:
    """Scoped forced regeneration for exactly the (champ_a, champ_b, role)
    triples in `targets` -- e.g. rows found contaminated by a since-fixed
    bug in champion_text(). Unlike run_precompute_batch, this deletes each
    target pair's existing Advice + MatchupStat rows (this patch only) --
    but only *after* a real regeneration for that same pair has already
    passed the grounding/section-split check, never before. Deleting first
    was tried and reverted: a real run against this pipeline hit a
    genuine (deterministic, greedy-decoded) grounding failure on one of
    the two target pairs, unrelated to markup -- deleting before checking
    would have destroyed that pair's only row for nothing. Old row is left
    completely alone if regeneration doesn't pass.

    Deliberately does NOT touch any row outside `targets`: only pairs whose
    (champ_a, champ_b, role) is in `targets` are deleted or regenerated.
    This is the mistake documented in phase3-eager-tier-precompute.md's
    "Idempotency" section (an overly broad check once regenerated all 109
    candidate pairs instead of the intended subset) -- guarded against here
    by scoping every delete/select to one exact triple at a time, never a
    broader existence check.

    `pairs` defaults to building real context (rank_real_candidate_pairs +
    build_pair_with_context) for exactly `targets`; pass explicit `pairs`
    (same shape run_precompute_batch expects) to avoid the real Data
    Dragon/CSV calls, e.g. in tests.

    `sampling_retry` (default False -- does not change the default,
    deterministic path used by run_precompute_batch or any existing
    force_regenerate_pairs caller): when True, a pair whose greedy
    generation fails grounding/section-split gets up to
    MAX_SAMPLING_RETRIES more attempts with SAMPLING_GEN_KWARGS before
    being counted as skipped. Opt-in per-call, not a global default, since
    it makes generation non-deterministic for whichever pairs use it.
    """
    if pairs is None:
        candidates = {
            (r["champ_a"], r["champ_b"], r["role"]): r for r in rank_real_candidate_pairs()
        }
        pairs = [build_pair_with_context(candidates[t]) for t in targets if t in candidates]

    pairs_by_key = {(p["champ_a"], p["champ_b"], p["role"]): p for p in pairs}

    session = sessionmaker(bind=engine)()
    written_pairs, skipped = [], []
    model = tokenizer = None
    try:
        for target in targets:
            pair = pairs_by_key.get(target)
            if pair is None:
                skipped.append({"champ_a": target[0], "champ_b": target[1], "role": target[2],
                                 "reason": "no_real_context_available"})
                continue

            if model is None:
                model, tokenizer = load_model_and_tokenizer(adapter_dir)

            check_fn = _generate_and_check_pair_with_sampling_retry if sampling_retry else _generate_and_check_pair
            check = check_fn(pair, model, tokenizer, max_new_tokens)
            if not check["passed"]:
                # Old row (if any) is untouched -- nothing deleted yet.
                skipped.append(check)
                continue

            # Only now, with a real passing regeneration in hand, delete
            # exactly this pair's existing rows (this patch only) -- never
            # a broader match. rank_bracket comes from `pair`, itself
            # derived only from this same target, not a wildcard.
            session.execute(delete(Advice).where(
                Advice.champ_a == pair["champ_a"], Advice.champ_b == pair["champ_b"],
                Advice.role == pair["role"], Advice.rank_bracket == pair["rank_bracket"],
                Advice.patch == patch,
            ))
            session.execute(delete(MatchupStat).where(
                MatchupStat.champ_a == pair["champ_a"], MatchupStat.champ_b == pair["champ_b"],
                MatchupStat.role == pair["role"], MatchupStat.rank_bracket == pair["rank_bracket"],
                MatchupStat.patch == patch,
            ))
            written_pairs.append(_write_pair_sections(session, pair, patch, check["sections"]))
    finally:
        session.close()

    return {"written_pairs": written_pairs, "skipped": skipped}


if __name__ == "__main__":
    from app.db_migrate import migrate

    server, engine = migrate()
    try:
        result = run_precompute_batch("16.15.1", engine=engine)
        print(json.dumps(result, indent=2, default=str))
        print(f"PRECOMPUTE_DONE written={len(result['written_pairs'])} "
              f"skipped={len(result['skipped'])} already_present={len(result['already_present'])}")
    finally:
        engine.dispose()
        server.cleanup()
