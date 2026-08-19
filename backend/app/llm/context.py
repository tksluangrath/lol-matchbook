"""
Live context builder for the /ask follow-up path (docs/build-plan.md's
real-time complement to the precomputed /advice path).

Reuses, unmodified, the exact context-block shape the qualitative adapter
was actually trained/tested against:

- champion_text() (app.retrieval.index) -- markup-stripped kit text, the
  same source both qa_generation.py and app.data_pipeline.precompute use.
- ability_whitelist_block() / fetch_champion_detail() (app.finetune.
  qualitative_advice) -- the real Data Dragon detail fetch + exact-spelling
  ability-name whitelist already validated there.

Real root cause found (docs/decisions/phase4-ask-quality-fix.md) for why
early /ask output read like a flat kit-tooltip dump instead of the causal,
win-condition-framed advice the same adapter produces via precompute.py
for this exact matchup/phase: two compounding gaps, not an adapter
capability problem --

1. This module never queried the Advice table at all. The already-
   generated, already-fact-checked precomputed early/mid/late text for the
   pair (demonstrably higher quality -- it's what the adapter was actually
   fine-tuned to produce) was completely absent from /ask's context. Fixed
   below: _lookup_precomputed_notes() pulls it in as grounding, same
   exact-match-then-wider-rank-fallback pattern _stats_block already uses.
2. The instruction line asked the model to "answer the user's question...
   specifically and concisely" -- a prompt shape the adapter was never
   fine-tuned on (it only ever saw qualitative_advice.build_generation_
   prompt()'s "write matchup advice in three labeled sections" framing
   during training). Rewritten below to ask for the same win-condition-
   first, causally-reasoned register the adapter actually learned,
   redirected at the live question instead of the fixed three-section format.
"""
from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finetune.qualitative_advice import ability_whitelist_block, fetch_champion_detail
from app.models import Advice, MatchupStat
from app.retrieval.index import champion_text

NO_DATA_NOTE = "No observed match data yet for this matchup at this rank."

# No real win-rate percentage exists to ground a citation against -- any
# percentage the model cites in this case is definitionally ungrounded, so
# fact_grounding_check should flag it, not silently pass it. Chosen far
# outside any real percentage range so no legitimate cite can match by luck.
NO_STAT_SENTINEL_PCT = -1000.0


class AskContext(NamedTuple):
    prompt: str
    grounding_source: str
    win_rate_pct: float


def _lookup_stat(db: Session, champ_a: str, champ_b: str, role: str, rank: str) -> MatchupStat | None:
    """Latest-patch MatchupStat row for the exact (champ_a, champ_b, role,
    rank) -- any phase, since precompute.py's own docstring notes there is
    one real win_rate/sample_size number per matchup, not three (all three
    phase rows carry identical numbers). Same func.max(patch) pattern
    routers/advice.py's _lookup already uses."""
    latest_patch = db.execute(
        select(func.max(MatchupStat.patch)).where(
            MatchupStat.champ_a == champ_a, MatchupStat.champ_b == champ_b,
            MatchupStat.role == role, MatchupStat.rank_bracket == rank,
        )
    ).scalar()
    if latest_patch is None:
        return None
    return db.execute(
        select(MatchupStat).where(
            MatchupStat.champ_a == champ_a, MatchupStat.champ_b == champ_b,
            MatchupStat.role == role, MatchupStat.rank_bracket == rank,
            MatchupStat.patch == latest_patch,
        ).order_by(MatchupStat.phase).limit(1)
    ).scalars().first()


def _stats_block(db: Session, champ_a: str, champ_b: str, role: str, rank: str) -> tuple[str, float]:
    """Real stats sentence (or NO_DATA_NOTE fallback), same format as
    app.data_pipeline.precompute.build_pair_with_context's context_block,
    plus the real win_rate_pct for grounding (NO_STAT_SENTINEL_PCT if no
    real row exists anywhere for this pair/role).

    Fallback chosen (mirrors routers/advice.py's own lazy-tier fallback
    rather than inventing a new one): if there's no row at the exact rank,
    widen to any rank_bracket that does have a row for this
    (champ_a, champ_b, role) -- same "fall back to a wider rank bracket"
    behavior docs/system-design.md's Error Handling section specifies and
    routers/advice.py._lookup already implements for the precomputed path.
    """
    stat = _lookup_stat(db, champ_a, champ_b, role, rank)
    if stat is None:
        wider_rank_row = db.execute(
            select(MatchupStat.rank_bracket)
            .where(MatchupStat.champ_a == champ_a, MatchupStat.champ_b == champ_b, MatchupStat.role == role)
            .limit(1)
        ).first()
        if wider_rank_row is not None:
            stat = _lookup_stat(db, champ_a, champ_b, role, wider_rank_row[0])

    if stat is None:
        return NO_DATA_NOTE, NO_STAT_SENTINEL_PCT

    game_word = "game" if stat.sample_size == 1 else "games"
    win_rate_pct = round(stat.win_rate * 100)
    return (
        f"Context: {stat.sample_size} {game_word} observed this patch between "
        f"{champ_a} and {champ_b} in the {role} lane. {champ_a} win rate: {win_rate_pct}%."
    ), float(win_rate_pct)


def _lookup_precomputed_advice(db: Session, champ_a: str, champ_b: str, role: str, rank: str) -> dict[str, str] | None:
    """Real precomputed early/mid/late Advice text for this pair, if any --
    same exact-match-then-wider-rank-bracket-fallback pattern as
    _stats_block, and the same real-column read routers/advice.py._lookup
    uses. Returns None (not fabricated) if nothing is precomputed, or if
    the only rows found are an abstention (no real advice text to ground on).
    """

    def _rows_at(rank_bracket: str) -> dict[str, str] | None:
        latest_patch = db.execute(
            select(func.max(Advice.patch)).where(
                Advice.champ_a == champ_a, Advice.champ_b == champ_b,
                Advice.role == role, Advice.rank_bracket == rank_bracket,
            )
        ).scalar()
        if latest_patch is None:
            return None
        rows = db.execute(
            select(Advice).where(
                Advice.champ_a == champ_a, Advice.champ_b == champ_b, Advice.role == role,
                Advice.rank_bracket == rank_bracket, Advice.patch == latest_patch,
            )
        ).scalars().all()
        if not rows or any(r.is_abstention for r in rows):
            return None
        by_phase = {r.phase: r.text for r in rows if r.text}
        return by_phase or None

    found = _rows_at(rank)
    if found is not None:
        return found

    wider_rank_row = db.execute(
        select(Advice.rank_bracket)
        .where(Advice.champ_a == champ_a, Advice.champ_b == champ_b, Advice.role == role)
        .limit(1)
    ).first()
    if wider_rank_row is not None:
        return _rows_at(wider_rank_row[0])
    return None


def _precomputed_notes_block(precomputed: dict[str, str] | None) -> str:
    if not precomputed:
        return ""
    lines = ["Precomputed strategic notes for this matchup (already written, real, and fact-checked):"]
    for phase in ("early", "mid", "late"):
        if phase in precomputed:
            lines.append(f"{phase.capitalize()}: {precomputed[phase]}")
    return "\n".join(lines) + "\n"


def build_ask_context(db: Session, champ_a: str, champ_b: str, role: str, rank: str, question: str) -> AskContext:
    """Assembles the live /ask prompt: real stats block (or its fallback),
    the real precomputed early/mid/late advice for this matchup if any
    exists (grounding the model in the same causally-reasoned content the
    adapter was actually trained to produce, instead of asking it to
    re-derive strategy from raw kit blurbs alone), real markup-stripped
    kit text for both champions, the ability-name whitelist, and the
    user's real question -- with an instruction asking for the same
    win-condition-first register precompute.py's prompt shape trains the
    adapter toward, redirected at the specific question instead of a fixed
    three-section format.

    Returns the real facts (grounding_source, win_rate_pct) alongside the
    prompt so the caller can run a real fact-grounding check on the
    generated response, the same check precompute.py's pipeline already
    gates writes on."""
    stats_block, win_rate_pct = _stats_block(db, champ_a, champ_b, role, rank)
    precomputed = _lookup_precomputed_advice(db, champ_a, champ_b, role, rank)
    notes_block = _precomputed_notes_block(precomputed)

    champ_a_detail = fetch_champion_detail(champ_a)
    champ_b_detail = fetch_champion_detail(champ_b)
    champ_a_kit = f"{champ_a} kit: {champion_text(champ_a_detail)}"
    champ_b_kit = f"{champ_b} kit: {champion_text(champ_b_detail)}"
    whitelist = ability_whitelist_block(champ_a, champ_a_detail, champ_b, champ_b_detail)

    grounding_source = f"{notes_block}{champ_a_kit}\n{champ_b_kit}\n{whitelist}"

    prompt = (
        f"{stats_block}\n{notes_block}{champ_a_kit}\n{champ_b_kit}\n{whitelist}\n"
        "Instruction: Using only the facts and precomputed notes given "
        "above, answer the user's question below. Start with a one- or "
        "two-sentence win condition: who should win this matchup if both "
        "play correctly, and the specific reason why. Then explain the key "
        "levers that decide it -- do not restate ability descriptions one "
        "by one; use them only to support your reasoning. Directly answer "
        "the question asked. Do not cite any ability, item, or statistic "
        "that is not stated above.\n"
        f"Question: {question}"
    )

    return AskContext(prompt=prompt, grounding_source=grounding_source, win_rate_pct=win_rate_pct)
