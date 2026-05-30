from __future__ import annotations


def test_graph_cites(client):
    resp = client.get("/api/papers/W1/graph", params={"direction": "cites"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["focus"]["id"] == "W1"
    assert body["direction"] == "cites"
    assert body["total_related"] == 2
    assert body["shown"] == 2
    assert body["live"] is False

    neighbor_ids = {n["id"] for n in body["nodes"] if not n["is_focus"]}
    assert neighbor_ids == {"W2", "W5"}
    for edge in body["edges"]:
        assert edge["source"] == "W1"
        assert edge["target"] in {"W2", "W5"}

    stub = next(n for n in body["nodes"] if n["id"] == "W5")
    assert stub["title"] is None


def test_graph_cited_by_uses_total_count(client):
    resp = client.get("/api/papers/W1/graph", params={"direction": "cited_by"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_related"] == 1000
    assert body["shown"] == 1
    neighbor = next(n for n in body["nodes"] if not n["is_focus"])
    assert neighbor["id"] == "W3"
    assert body["edges"][0] == {"source": "W3", "target": "W1"}


def test_graph_respects_limit_and_orders_by_citations(client):
    resp = client.get("/api/papers/W1/graph", params={"direction": "cites", "limit": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["shown"] == 1
    neighbor = next(n for n in body["nodes"] if not n["is_focus"])
    assert neighbor["id"] == "W2"


def test_graph_not_found(client):
    resp = client.get("/api/papers/W999/graph")
    assert resp.status_code == 404


def test_graph_direction_validation(client):
    resp = client.get("/api/papers/W1/graph", params={"direction": "sideways"})
    assert resp.status_code == 422


def test_graph_live_augments_cited_by(client, monkeypatch):
    import app.api.routers.graph as graph_router

    def fake_live(focus_id, existing, limit):
        node = {
            "id": "WLIVE",
            "title": "Live citing paper",
            "cited_by_count": 7,
            "publication_year": 2020,
            "is_open_access": True,
            "is_focus": False,
        }
        return [node], [{"source": "WLIVE", "target": focus_id}]

    monkeypatch.setattr(graph_router, "fetch_live_cited_by", fake_live)

    resp = client.get(
        "/api/papers/W1/graph", params={"direction": "cited_by", "live": "true"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["live"] is True
    assert body["shown"] == 2
    assert "WLIVE" in {n["id"] for n in body["nodes"]}
    assert {"source": "WLIVE", "target": "W1"} in body["edges"]


def test_graph_live_failure_degrades_gracefully(client, monkeypatch):
    import app.api.routers.graph as graph_router

    def boom(focus_id, existing, limit):
        raise RuntimeError("openalex down")

    monkeypatch.setattr(graph_router, "fetch_live_cited_by", boom)

    resp = client.get(
        "/api/papers/W1/graph", params={"direction": "cited_by", "live": "true"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["live"] is False
    assert body["shown"] == 1
