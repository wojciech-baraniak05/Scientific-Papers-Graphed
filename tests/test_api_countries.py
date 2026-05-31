from __future__ import annotations


def test_field_country_ranking_by_papers(client):
    resp = client.get("/api/fields/22/country-ranking", params={"order_by": "papers"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope_type"] == "field"
    assert body["scope_id"] == "22"

    items = body["items"]
    assert [r["country_code"] for r in items] == ["NL", "US"]

    nl = items[0]
    assert nl["paper_count"] == 2
    assert nl["total_citations"] == 1500
    assert nl["num_universities"] == 50
    assert nl["papers_per_gdp"] == 0.2
    assert nl["papers_per_university"] == 0.04
    assert nl["top_paper"]["id"] == "W1"
    assert nl["top_paper"]["cited_by_count"] == 1000


def test_field_country_ranking_ratio_nulls_sort_last(client):
    resp = client.get("/api/fields/11/country-ranking", params={"order_by": "papers_per_gdp"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [r["country_code"] for r in items] == ["US", "ZZ"]
    assert items[-1]["country_code"] == "ZZ"
    assert items[-1]["papers_per_gdp"] is None
    assert items[-1]["papers_per_university"] is None


def test_field_not_found(client):
    resp = client.get("/api/fields/99/country-ranking")
    assert resp.status_code == 404


def test_field_ranking_order_by_validation(client):
    resp = client.get("/api/fields/22/country-ranking", params={"order_by": "magic"})
    assert resp.status_code == 422


def test_domain_country_ranking(client):
    resp = client.get("/api/domains/3/country-ranking", params={"order_by": "papers"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope_type"] == "domain"
    assert [r["country_code"] for r in body["items"]] == ["NL", "US"]


def test_domain_not_found(client):
    resp = client.get("/api/domains/9/country-ranking")
    assert resp.status_code == 404
