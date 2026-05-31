from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.cache import TTLCache
from app.api.deps import get_db
from app.repository import countries as repo
from app.schemas.schemas import FieldsResponse

router = APIRouter()

_fields_cache = TTLCache(ttl_seconds=300.0)


@router.get("/fields", response_model=FieldsResponse)
def list_fields(session: Session = Depends(get_db)) -> dict:
    cached = _fields_cache.get("fields")
    if cached is not None:
        return cached
    data = repo.list_fields(session)
    _fields_cache.set("fields", data)
    return data
