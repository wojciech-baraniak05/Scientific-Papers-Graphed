from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.api.cache import TTLCache
from app.api.deps import get_db
from app.db.models import Paper
from app.repository import countries as repo
from app.schemas.schemas import CountryRankingResponse, RankingOrderBy

router = APIRouter()

_ranking_cache = TTLCache(ttl_seconds=300.0)


def _ranking(
    session: Session,
    scope_type: str,
    scope_col: ColumnElement,
    scope_val: str,
    order_by: RankingOrderBy,
    limit: int,
) -> dict:
    key = (scope_type, scope_val, order_by.value, limit)
    cached = _ranking_cache.get(key)
    if cached is not None:
        return cached
    items = repo.country_ranking(
        session,
        scope_col=scope_col,
        scope_val=scope_val,
        order_by=order_by.value,
        limit=limit,
    )
    data = {
        "scope_type": scope_type,
        "scope_id": scope_val,
        "order_by": order_by.value,
        "count": len(items),
        "items": items,
    }
    _ranking_cache.set(key, data)
    return data


@router.get("/fields/{field_id}/country-ranking", response_model=CountryRankingResponse)
def field_country_ranking(
    field_id: str,
    order_by: RankingOrderBy = Query(RankingOrderBy.papers),
    limit: int = Query(30, ge=1, le=200),
    session: Session = Depends(get_db),
) -> dict:
    if not repo.field_exists(session, field_id):
        raise HTTPException(status_code=404, detail=f"Field {field_id!r} not found")
    return _ranking(session, "field", Paper.primary_field_id, field_id, order_by, limit)


@router.get("/domains/{domain_id}/country-ranking", response_model=CountryRankingResponse)
def domain_country_ranking(
    domain_id: str,
    order_by: RankingOrderBy = Query(RankingOrderBy.papers),
    limit: int = Query(30, ge=1, le=200),
    session: Session = Depends(get_db),
) -> dict:
    if not repo.domain_exists(session, domain_id):
        raise HTTPException(status_code=404, detail=f"Domain {domain_id!r} not found")
    return _ranking(session, "domain", Paper.primary_domain_id, domain_id, order_by, limit)
