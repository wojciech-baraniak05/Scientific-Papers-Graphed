from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repository import papers as repo
from app.repository.live import fetch_live_cited_by
from app.schemas.schemas import GraphDirection, GraphResponse

router = APIRouter()


@router.get("/papers/{paper_id}/graph", response_model=GraphResponse)
def get_paper_graph(
    paper_id: str,
    direction: GraphDirection = Query(GraphDirection.cites),
    limit: int = Query(50, ge=1, le=200),
    live: bool = Query(False, description="Augment cited_by from OpenAlex on demand"),
    session: Session = Depends(get_db),
) -> dict:
    graph = repo.get_graph(session, paper_id, direction.value, limit)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id!r} not found")

    neighbor_count = len(graph["nodes"]) - 1
    if live and direction == GraphDirection.cited_by and neighbor_count < limit:
        try:
            existing = {node["id"] for node in graph["nodes"]}
            extra_nodes, extra_edges = fetch_live_cited_by(
                paper_id, existing, limit - neighbor_count
            )
            graph["nodes"].extend(extra_nodes)
            graph["edges"].extend(extra_edges)
            graph["shown"] = len(graph["nodes"]) - 1
            graph["live"] = True
        except Exception as exc:
            logger.warning("Live cited-by augmentation failed for {}: {}", paper_id, exc)

    return graph
