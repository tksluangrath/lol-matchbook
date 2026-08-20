"""
POST /report -- lets a player flag a bug or a wrong-looking matchup call
from the chat UI's /report command. Pure write, no model call: one real
row in `reports` per submission, for a human to triage later. No
automated action is taken on a report here -- that's a deliberate scope
cut, matching /refresh's own "explicitly user/operator triggered, nothing
automatic" stance.
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Report

router = APIRouter()


class ReportRequest(BaseModel):
    category: Literal["bug", "matchup_mistake"]
    message: str
    champ_a: str | None = None
    champ_b: str | None = None
    role: str | None = None
    rank: str | None = None


@router.post("/report")
def report(body: ReportRequest, db: Session = Depends(get_db)):
    row = Report(
        category=body.category,
        message=body.message,
        champ_a=body.champ_a,
        champ_b=body.champ_b,
        role=body.role,
        rank_bracket=body.rank,
    )
    db.add(row)
    db.commit()
    return {"status": "received"}
