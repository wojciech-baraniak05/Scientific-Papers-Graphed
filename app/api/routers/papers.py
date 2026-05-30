from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repository import papers as repo
from app.schemas.schemas import PaperDetail, PaperSummary

router = APIRouter()


@router.get("/papers/search", response_model=list[PaperSummary])
def search_papers(
    q: str | None = Query(None, description="Title substring to match"),
    field_id: str | None = Query(None, description="Restrict to an OpenAlex field id"),
    domain_id: str | None = Query(None, description="Restrict to an OpenAlex domain id"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[dict]:
    return repo.search_papers(session, q, field_id, domain_id, limit)


@router.get("/papers/{paper_id}", response_model=PaperDetail)
def get_paper(
    paper_id: str,
    session: Session = Depends(get_db),
) -> dict:
    detail = repo.paper_detail(session, paper_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")
    return detail
