from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.db.models import Author, Paper, PaperAuthor, PaperReference

_POSITION_ORDER = case(
    (PaperAuthor.author_position == "first", 0),
    (PaperAuthor.author_position == "middle", 1),
    (PaperAuthor.author_position == "last", 2),
    else_=3,
)


def get_paper(session: Session, paper_id: str) -> Paper | None:
    return session.get(Paper, paper_id)


def get_paper_authors(session: Session, paper_id: str) -> list[dict]:
    rows = session.execute(
        select(
            Author.id,
            Author.display_name,
            Author.orcid,
            PaperAuthor.author_position,
        )
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .where(PaperAuthor.paper_id == paper_id)
        .order_by(_POSITION_ORDER, Author.display_name)
    ).all()
    return [
        {
            "id": row.id,
            "display_name": row.display_name,
            "orcid": row.orcid,
            "author_position": row.author_position,
        }
        for row in rows
    ]


def paper_detail(session: Session, paper_id: str) -> dict | None:
    paper = get_paper(session, paper_id)
    if paper is None:
        return None
    return {
        "id": paper.id,
        "doi": paper.doi,
        "title": paper.title,
        "publication_year": paper.publication_year,
        "cited_by_count": paper.cited_by_count,
        "referenced_works_count": paper.referenced_works_count,
        "is_open_access": paper.is_open_access,
        "oa_status": paper.oa_status,
        "oa_url": paper.oa_url,
        "is_educational": paper.is_educational,
        "primary_field_id": paper.primary_field_id,
        "primary_field_name": paper.primary_field_name,
        "primary_domain_id": paper.primary_domain_id,
        "primary_domain_name": paper.primary_domain_name,
        "abstract": paper.abstract,
        "authors": get_paper_authors(session, paper_id),
    }


def search_papers(
    session: Session,
    q: str | None,
    field_id: str | None,
    domain_id: str | None,
    limit: int,
) -> list[dict]:
    stmt = select(Paper).where(Paper.ingested.is_(True), Paper.title.is_not(None))
    if q:
        stmt = stmt.where(Paper.title.ilike(f"%{q}%"))
    if field_id:
        stmt = stmt.where(Paper.primary_field_id == field_id)
    if domain_id:
        stmt = stmt.where(Paper.primary_domain_id == domain_id)
    stmt = stmt.order_by(Paper.cited_by_count.desc()).limit(limit)
    papers = session.execute(stmt).scalars().all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "doi": p.doi,
            "cited_by_count": p.cited_by_count,
            "publication_year": p.publication_year,
            "is_open_access": p.is_open_access,
            "primary_field_id": p.primary_field_id,
            "primary_field_name": p.primary_field_name,
            "primary_domain_id": p.primary_domain_id,
            "primary_domain_name": p.primary_domain_name,
        }
        for p in papers
    ]


def get_graph(
    session: Session, paper_id: str, direction: str, limit: int
) -> dict | None:
    focus = get_paper(session, paper_id)
    if focus is None:
        return None

    neighbor = aliased(Paper)
    if direction == "cites":
        join_col = PaperReference.referenced_id
        edge_cond = PaperReference.citing_id == paper_id
        declared_total = focus.referenced_works_count
    else:
        join_col = PaperReference.citing_id
        edge_cond = PaperReference.referenced_id == paper_id
        declared_total = focus.cited_by_count

    rows = session.execute(
        select(
            neighbor.id,
            neighbor.title,
            neighbor.cited_by_count,
            neighbor.publication_year,
            neighbor.is_open_access,
        )
        .join(PaperReference, join_col == neighbor.id)
        .where(edge_cond)
        .order_by(neighbor.cited_by_count.desc())
        .limit(limit)
    ).all()

    edge_count = session.execute(
        select(func.count()).select_from(PaperReference).where(edge_cond)
    ).scalar() or 0

    nodes: list[dict] = [
        {
            "id": focus.id,
            "title": focus.title,
            "cited_by_count": focus.cited_by_count,
            "publication_year": focus.publication_year,
            "is_open_access": focus.is_open_access,
            "is_focus": True,
        }
    ]
    edges: list[dict] = []
    for row in rows:
        nodes.append(
            {
                "id": row.id,
                "title": row.title,
                "cited_by_count": row.cited_by_count,
                "publication_year": row.publication_year,
                "is_open_access": row.is_open_access,
                "is_focus": False,
            }
        )
        if direction == "cites":
            edges.append({"source": focus.id, "target": row.id})
        else:
            edges.append({"source": row.id, "target": focus.id})

    total_related = declared_total if declared_total is not None else edge_count

    return {
        "focus": {
            "id": focus.id,
            "title": focus.title,
            "cited_by_count": focus.cited_by_count,
        },
        "direction": direction,
        "total_related": total_related,
        "shown": len(rows),
        "live": False,
        "nodes": nodes,
        "edges": edges,
    }
