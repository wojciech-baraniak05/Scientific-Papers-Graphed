from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repository import papers as repo
from app.schemas.schemas import GraphDirection, GraphResponse

router = APIRouter()


@router.get("/papers/{paper_id}/graph", response_model=GraphResponse)
def get_paper_graph(
    paper_id: str,
    direction: GraphDirection = Query(GraphDirection.cites),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> dict:
    graph = repo.get_graph(session, paper_id, direction.value, limit)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")

    return graph
