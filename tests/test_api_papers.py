from __future__ import annotations


def test_search_orders_by_citations_and_excludes_stubs(client):
    resp = client.get("/api/papers/search")
    assert resp.status_code == 200
    items = resp.json()
    ids = [item["id"] for item in items]
    assert ids == ["W1", "W2", "W3", "W4"]
    assert "W5" not in ids


def test_search_by_query(client):
    resp = client.get("/api/papers/search", params={"q": "neural"})
    assert resp.status_code == 200
    items = resp.json()
    assert [item["id"] for item in items] == ["W2"]


def test_search_by_field(client):
    resp = client.get("/api/papers/search", params={"field_id": "22"})
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert ids == {"W1", "W2"}


def test_search_limit_validation(client):
    resp = client.get("/api/papers/search", params={"limit": 0})
    assert resp.status_code == 422


def test_paper_detail(client):
    resp = client.get("/api/papers/W1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "W1"
    assert body["doi"] == "10.1/w1"
    assert body["cited_by_count"] == 1000
    assert body["is_open_access"] is True
    assert body["oa_status"] == "gold"
    assert body["abstract"] == "Abstract one"
    assert [a["display_name"] for a in body["authors"]] == ["Alice", "Bob"]
    assert body["authors"][0]["author_position"] == "first"


def test_paper_detail_not_found(client):
    resp = client.get("/api/papers/W999")
    assert resp.status_code == 404
