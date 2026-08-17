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

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.finetune.eval import generate, load_model_and_tokenizer
from app.finetune.qualitative_advice import fact_grounding_check
from app.models import Advice, MatchupStat

DATA_DIR = Path(__file__).resolve().parents[1] / "finetune" / "data"
QUAL_HELDOUT_PATH = DATA_DIR / "qualitative_advice_heldout.jsonl"
HELDOUT_CONTEXT_PATH = DATA_DIR / "heldout_context.jsonl"
DEFAULT_ADAPTER_DIR = (
    Path(__file__).resolve().parents[1] / "finetune" / "artifacts" / "smoke-adapter-qualitative-dedicated-v2"
)
MAX_NEW_TOKENS = 400

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

            output = generate(model, tokenizer, pair["generation_prompt"], max_new_tokens)
            expected_pct = round(pair["win_rate"] * 100)
            grounding = fact_grounding_check(output, pair["generation_prompt"], expected_pct)
            sections = split_into_sections(output)

            if sections is None or not grounding["passed"]:
                skipped.append({
                    "champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"],
                    "reason": "could_not_split_sections" if sections is None else "grounding_failed",
                    "invented_phrases": grounding["invented_phrases"],
                    "model_output": output,
                })
                continue

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
            written_pairs.append({"champ_a": pair["champ_a"], "champ_b": pair["champ_b"], "role": pair["role"]})
    finally:
        session.close()

    return {"written_pairs": written_pairs, "already_present": already_present, "skipped": skipped}


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
