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

Stats-block format: app.data_pipeline.precompute.build_pair_with_context()
is the real, currently-used shape (not app.finetune.qualitative_advice.
build_generation_prompt(), which is the offline training-data-generation
path and appends its own three-section "Instruction:" line meant for
regenerating precomputed advice, not answering a live question). This
module reuses precompute.py's plain "Context: N games observed..." sentence
verbatim and appends a different, question-specific instruction instead.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finetune.qualitative_advice import ability_whitelist_block, fetch_champion_detail
from app.models import MatchupStat
from app.retrieval.index import champion_text

NO_DATA_NOTE = "No observed match data yet for this matchup at this rank."


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


def _stats_block(db: Session, champ_a: str, champ_b: str, role: str, rank: str) -> str:
    """Real stats sentence, same format as
    app.data_pipeline.precompute.build_pair_with_context's context_block.

    Fallback chosen (mirrors routers/advice.py's own lazy-tier fallback
    rather than inventing a new one): if there's no row at the exact rank,
    widen to any rank_bracket that does have a row for this
    (champ_a, champ_b, role) -- same "fall back to a wider rank bracket"
    behavior docs/system-design.md's Error Handling section specifies and
    routers/advice.py._lookup already implements for the precomputed path.
    If there is truly no row for this pair/role at any rank, the stats
    line is omitted entirely and replaced with an explicit "no observed
    data yet" note -- there is no archetype-blurb equivalent here because,
    unlike /advice, /ask still has a real question and real kit context to
    answer from; a missing win-rate stat alone is not an abstention case.
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
        return NO_DATA_NOTE

    game_word = "game" if stat.sample_size == 1 else "games"
    win_rate_pct = round(stat.win_rate * 100)
    return (
        f"Context: {stat.sample_size} {game_word} observed this patch between "
        f"{champ_a} and {champ_b} in the {role} lane. {champ_a} win rate: {win_rate_pct}%."
    )


def build_ask_context(db: Session, champ_a: str, champ_b: str, role: str, rank: str, question: str) -> str:
    """Assembles the live /ask prompt: real stats block (or its fallback,
    see _stats_block), real markup-stripped kit text for both champions,
    the same ability-name whitelist the adapter was trained against, and
    the user's real question -- with an instruction line asking the
    adapter to answer that question specifically, not to regurgitate the
    early/mid/late matchup-advice format the precompute path's own
    Instruction line asks for."""
    stats_block = _stats_block(db, champ_a, champ_b, role, rank)

    champ_a_detail = fetch_champion_detail(champ_a)
    champ_b_detail = fetch_champion_detail(champ_b)
    champ_a_kit = f"{champ_a} kit: {champion_text(champ_a_detail)}"
    champ_b_kit = f"{champ_b} kit: {champion_text(champ_b_detail)}"
    whitelist = ability_whitelist_block(champ_a, champ_a_detail, champ_b, champ_b_detail)

    return (
        f"{stats_block}\n{champ_a_kit}\n{champ_b_kit}\n{whitelist}\n"
        "Instruction: Using only the facts given above, answer the user's "
        "question below specifically and concisely. Do not cite any "
        "ability, item, or statistic that is not stated above.\n"
        f"Question: {question}"
    )
