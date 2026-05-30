from __future__ import annotations

from app.config import get_settings
from app.ingestion.openalex_client import STUB_SELECT, OpenAlexClient
from app.processing.transform import short_id


def fetch_live_cited_by(
    focus_id: str, existing_ids: set[str], limit: int
) -> tuple[list[dict], list[dict]]:
    settings = get_settings()
    nodes: list[dict] = []
    edges: list[dict] = []
    seen = set(existing_ids)
    seen.add(focus_id)

    with OpenAlexClient(
        email=settings.openalex_email,
        api_key=settings.openalex_api_key,
        base_url=settings.openalex_base_url,
        timeout=settings.http_timeout,
        max_retries=settings.http_max_retries,
        backoff_base=settings.http_backoff_base,
    ) as client:
        works = client.iter_works(
            filter=f"cites:{focus_id}",
            select=STUB_SELECT,
            per_page=min(limit, 200),
            max_records=limit,
        )
        for work in works:
            sid = short_id(work.get("id"))
            if not sid or sid in seen:
                continue
            seen.add(sid)
            oa = work.get("open_access") or {}
            nodes.append(
                {
                    "id": sid,
                    "title": work.get("title") or work.get("display_name"),
                    "cited_by_count": work.get("cited_by_count"),
                    "publication_year": work.get("publication_year"),
                    "is_open_access": oa.get("is_oa"),
                    "is_focus": False,
                }
            )
            edges.append({"source": sid, "target": focus_id})
            if len(nodes) >= limit:
                break

    return nodes, edges
