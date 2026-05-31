
def test_graph_cites(client):
    resp = client.get("/api/papers/W1/graph", params={"direction": "cites"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["focus"]["id"] == "W1"
    assert body["direction"] == "cites"
    assert body["total_related"] == 2
    assert body["shown"] == 2

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
