from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("API_TIMEOUT", "30"))


class ApiError(RuntimeError):
    pass


def _get(path: str, params: dict | None = None) -> object:
    url = f"{API_BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the API at {API_BASE_URL}: {exc}") from exc

    if resp.status_code == 404:
        raise ApiError(f"Not found: {path}")
    if resp.status_code >= 400:
        raise ApiError(f"API error {resp.status_code} on {path}: {resp.text[:200]}")
    return resp.json()


def get_health() -> dict:
    try:
        data = _get("/api/health")
        return data if isinstance(data, dict) else {"status": "unknown", "database": "unknown"}
    except ApiError:
        return {"status": "down", "database": "down"}


@st.cache_data(ttl=300, show_spinner=False)
def get_fields() -> dict:
    return _get("/api/fields")


@st.cache_data(ttl=300, show_spinner=False)
def search_papers(
    q: str | None,
    field_id: str | None,
    domain_id: str | None,
    limit: int,
) -> list[dict]:
    params: dict[str, object] = {"limit": limit}
    if q:
        params["q"] = q
    if field_id:
        params["field_id"] = field_id
    if domain_id:
        params["domain_id"] = domain_id
    return _get("/api/papers/search", params)


@st.cache_data(ttl=300, show_spinner=False)
def get_paper(paper_id: str) -> dict:
    return _get(f"/api/papers/{paper_id}")


@st.cache_data(ttl=300, show_spinner=False)
def _get_graph_cached(paper_id: str, direction: str, limit: int) -> dict:
    return _get(
        f"/api/papers/{paper_id}/graph",
        {"direction": direction, "limit": limit, "live": False},
    )


def get_paper_graph(paper_id: str, direction: str, limit: int, live: bool) -> dict:
    if not live:
        return _get_graph_cached(paper_id, direction, limit)
    return _get(
        f"/api/papers/{paper_id}/graph",
        {"direction": direction, "limit": limit, "live": True},
    )


@st.cache_data(ttl=300, show_spinner=False)
def field_country_ranking(field_id: str, order_by: str, limit: int) -> dict:
    return _get(
        f"/api/fields/{field_id}/country-ranking",
        {"order_by": order_by, "limit": limit},
    )


@st.cache_data(ttl=300, show_spinner=False)
def domain_country_ranking(domain_id: str, order_by: str, limit: int) -> dict:
    return _get(
        f"/api/domains/{domain_id}/country-ranking",
        {"order_by": order_by, "limit": limit},
    )
