from __future__ import annotations


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_fields_list(client):
    resp = client.get("/api/fields")
    assert resp.status_code == 200
    body = resp.json()

    fields = {f["id"]: f for f in body["fields"]}
    assert "22" in fields
    assert "11" in fields
    assert fields["22"]["name"] == "Engineering"
    assert fields["22"]["paper_count"] == 2
    assert fields["11"]["paper_count"] == 2

    domains = {d["id"]: d for d in body["domains"]}
    assert "3" in domains
    assert "1" in domains
    assert domains["3"]["paper_count"] == 2
