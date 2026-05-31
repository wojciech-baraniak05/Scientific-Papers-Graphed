# REST API reference

Base URL (local): `http://localhost:8000`. Interactive Swagger UI at `/docs`,
OpenAPI JSON at `/openapi.json`. All responses are Pydantic-typed
([../app/schemas/schemas.py](../app/schemas/schemas.py)). Path params use the
**short** OpenAlex id form (`W2741809807`, `22`).

---

## Endpoints

| Method & path | Query params | Success | Errors |
|---|---|---|---|
| `GET /api/health` | — | `{status, database}` | — |
| `GET /api/fields` | — | `{fields[], domains[]}` | — |
| `GET /api/papers/search` | `q?`, `field_id?`, `domain_id?`, `limit=20 (1..100)` | `PaperSummary[]` | 422 |
| `GET /api/papers/{id}` | — | `PaperDetail` | 404 |
| `GET /api/papers/{id}/graph` | `direction=cites\|cited_by`, `limit=50 (1..200)`, `live=false` | `GraphResponse` | 404, 422 |
| `GET /api/fields/{field_id}/country-ranking` | `order_by=papers (enum)`, `limit=30 (1..200)` | `CountryRankingResponse` | 404, 422 |
| `GET /api/domains/{domain_id}/country-ranking` | `order_by=papers (enum)`, `limit=30 (1..200)` | `CountryRankingResponse` | 404, 422 |

`order_by` enum: `citations | papers | universities | gdp | population |
papers_per_gdp | papers_per_university | papers_per_capita`.

---

## Key response shapes

**`PaperDetail`** (right-hand panel, Tab 1): `id, doi, title, publication_year,
cited_by_count, referenced_works_count, is_open_access, oa_status, oa_url,
is_educational, primary_field_id/name, primary_domain_id/name, abstract,
authors[]{id, display_name, orcid, author_position}`.

**`GraphResponse`** (Tab 1 graph):
```json
{
  "focus": {"id": "W1", "title": "...", "cited_by_count": 12453},
  "direction": "cited_by",
  "total_related": 12453,
  "shown": 50,
  "live": false,
  "nodes": [{"id": "W1", "title": "...", "cited_by_count": 12453,
             "publication_year": 2015, "is_open_access": true, "is_focus": true}],
  "edges": [{"source": "W2", "target": "W1"}]
}
```
- `direction=cites` → edges where `citing_id = focus`; `total_related = referenced_works_count`.
- `direction=cited_by` → edges where `referenced_id = focus`; `total_related = cited_by_count` (the **full** count, independent of `shown`).
- `live=true` augments **`cited_by`** only from OpenAlex; failures degrade to DB-only.

**`CountryRankingRow`** (Tab 2):
```json
{
  "country_code": "NL",
  "country_name": "Netherlands",
  "paper_count": 4821,
  "total_citations": 1932044,
  "num_universities": 53,
  "gdp_usd": 1.01e12,
  "population": 17900000,
  "papers_per_gdp": 477.3,
  "papers_per_university": 91.0,
  "papers_per_capita": 269.3,
  "top_paper": {"id": "W...", "title": "...", "cited_by_count": 88123, "doi": "10.xxxx/..."}
}
```
Ratio units: `papers_per_gdp` = papers per 100B USD GDP, `papers_per_capita` =
papers per million capita. Ratios are `null` (sorted last) when GDP / population /
university data is missing or zero. The ranking response wraps the rows with
`scope_type`, `scope_id`, `order_by`, `count`, `items[]`.

---

## Status codes

- `200` success · `404` unknown paper / field / domain · `422` invalid query
  param (e.g. bad `direction` or `order_by`) · `500` clean JSON error
  (`{"detail": "Internal server error"}`), logged via loguru.
