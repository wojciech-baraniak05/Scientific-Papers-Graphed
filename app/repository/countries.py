from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Country, Field, Paper, PaperCountry


def list_fields(session: Session) -> dict:
    field_rows = session.execute(select(Field).order_by(Field.name)).scalars().all()

    field_counts = dict(
        session.execute(
            select(Paper.primary_field_id, func.count())
            .where(Paper.primary_field_id.is_not(None))
            .group_by(Paper.primary_field_id)
        ).all()
    )
    domain_counts = dict(
        session.execute(
            select(Paper.primary_domain_id, func.count())
            .where(Paper.primary_domain_id.is_not(None))
            .group_by(Paper.primary_domain_id)
        ).all()
    )

    fields = [
        {
            "id": f.id,
            "name": f.name,
            "domain_id": f.domain_id,
            "domain_name": f.domain_name,
            "paper_count": int(field_counts.get(f.id, 0)),
        }
        for f in field_rows
    ]

    domains: dict[str, dict] = {}
    for f in field_rows:
        if f.domain_id and f.domain_id not in domains:
            domains[f.domain_id] = {
                "id": f.domain_id,
                "name": f.domain_name,
                "paper_count": int(domain_counts.get(f.domain_id, 0)),
            }

    return {"fields": fields, "domains": sorted(domains.values(), key=lambda d: d["name"] or "")}


def field_exists(session: Session, field_id: str) -> bool:
    return session.get(Field, field_id) is not None


def domain_exists(session: Session, domain_id: str) -> bool:
    in_fields = session.execute(
        select(Field.id).where(Field.domain_id == domain_id).limit(1)
    ).first()
    if in_fields is not None:
        return True
    in_papers = session.execute(
        select(Paper.id).where(Paper.primary_domain_id == domain_id).limit(1)
    ).first()
    return in_papers is not None


def _ratio_per_100b_gdp(paper_count: int, gdp: float | None) -> float | None:
    if not gdp:
        return None
    return round(paper_count / (gdp / 1e11), 3)


def _ratio_per_university(paper_count: int, num_universities: int | None) -> float | None:
    if not num_universities:
        return None
    return round(paper_count / num_universities, 3)


def _ratio_per_million_capita(paper_count: int, population: int | None) -> float | None:
    if not population:
        return None
    return round(paper_count / (population / 1e6), 3)


def _build_row(
    code: str,
    name: str | None,
    paper_count: int,
    total_citations: int,
    num_universities: int | None,
    gdp: float | None,
    population: int | None,
) -> dict:
    return {
        "country_code": code,
        "country_name": name,
        "paper_count": paper_count,
        "total_citations": total_citations,
        "num_universities": num_universities,
        "gdp_usd": gdp,
        "population": population,
        "papers_per_100b_gdp": _ratio_per_100b_gdp(paper_count, gdp),
        "papers_per_university": _ratio_per_university(paper_count, num_universities),
        "papers_per_million_capita": _ratio_per_million_capita(paper_count, population),
        "top_paper": None,
    }


_SORT_KEYS: dict[str, Callable[[dict], float | int | None]] = {
    "citations": lambda r: r["total_citations"],
    "papers": lambda r: r["paper_count"],
    "universities": lambda r: r["num_universities"],
    "gdp": lambda r: r["gdp_usd"],
    "population": lambda r: r["population"],
    "papers_per_gdp": lambda r: r["papers_per_100b_gdp"],
    "papers_per_university": lambda r: r["papers_per_university"],
    "papers_per_capita": lambda r: r["papers_per_million_capita"],
}


def _sort_and_limit(rows: list[dict], order_by: str, limit: int) -> list[dict]:
    key_fn = _SORT_KEYS[order_by]
    rows.sort(key=lambda r: (key_fn(r) is None, -(key_fn(r) or 0)))
    return rows[:limit]


def _top_papers(
    session: Session, scope_col: ColumnElement, scope_val: str, codes: list[str]
) -> dict[str, dict]:
    if not codes:
        return {}
    rn = func.row_number().over(
        partition_by=PaperCountry.country_code,
        order_by=Paper.cited_by_count.desc(),
    ).label("rn")
    ranked = (
        select(
            PaperCountry.country_code.label("country_code"),
            Paper.id.label("id"),
            Paper.title.label("title"),
            Paper.cited_by_count.label("cited_by_count"),
            Paper.doi.label("doi"),
            rn,
        )
        .join(Paper, Paper.id == PaperCountry.paper_id)
        .where(scope_col == scope_val, PaperCountry.country_code.in_(codes))
        .subquery()
    )
    rows = session.execute(
        select(
            ranked.c.country_code,
            ranked.c.id,
            ranked.c.title,
            ranked.c.cited_by_count,
            ranked.c.doi,
        ).where(ranked.c.rn == 1)
    ).all()
    return {
        row.country_code: {
            "id": row.id,
            "title": row.title,
            "cited_by_count": row.cited_by_count,
            "doi": row.doi,
        }
        for row in rows
    }


def country_ranking(
    session: Session,
    *,
    scope_col: ColumnElement,
    scope_val: str,
    order_by: str,
    limit: int,
) -> list[dict]:
    agg = session.execute(
        select(
            PaperCountry.country_code.label("country_code"),
            func.count().label("paper_count"),
            func.coalesce(func.sum(Paper.cited_by_count), 0).label("total_citations"),
        )
        .join(Paper, Paper.id == PaperCountry.paper_id)
        .where(scope_col == scope_val)
        .group_by(PaperCountry.country_code)
    ).all()

    if not agg:
        return []

    codes = [row.country_code for row in agg]
    meta = {
        c.code: c
        for c in session.execute(
            select(Country).where(Country.code.in_(codes))
        ).scalars()
    }

    rows: list[dict] = []
    for row in agg:
        country = meta.get(row.country_code)
        rows.append(
            _build_row(
                code=row.country_code,
                name=country.name if country else None,
                paper_count=int(row.paper_count),
                total_citations=int(row.total_citations or 0),
                num_universities=country.num_universities if country else None,
                gdp=country.gdp_usd if country else None,
                population=country.population if country else None,
            )
        )

    rows = _sort_and_limit(rows, order_by, limit)

    page_codes = [r["country_code"] for r in rows]
    top = _top_papers(session, scope_col, scope_val, page_codes)
    for r in rows:
        r["top_paper"] = top.get(r["country_code"])

    return rows
