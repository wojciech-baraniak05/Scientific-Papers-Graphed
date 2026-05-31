# Part 2 — Backend API (FastAPI)

This document describes every file created for **Part 2** of the Paper Citation
Explorer (see [CLAUDE.md](CLAUDE.md) for the overall plan and [part1.md](part1.md)
for the data foundation it builds on), what each file does, and how Part 3 (the
Streamlit frontend) will consume it. The last sections record the design decisions
taken to resolve plan ambiguities, and how to verify the code right now.

---

## 1. What Part 2 delivers

Part 2 is the **API owner**: it sits directly on top of the MySQL schema frozen by
Part 1 and exposes it as a typed, documented REST API. It never re-implements
ingestion — it reads what the Part 1 pipeline wrote.

It maps onto the top two layers below the frontend in the architecture:

```
storage (MySQL, Part 1)
        │  SQLAlchemy ORM (read-only sessions)
repository / query layer   ← paper detail · search · graph · country ranking
        │  plain row dicts
FastAPI routers + Pydantic schemas   ← validation, HTTP codes, auto Swagger
        │  JSON over HTTP
frontend (Streamlit, Part 3)
```

**Done-when (met):** every endpoint in §8 of the plan returns correct typed JSON
against a seeded DB, Swagger renders the full contract at `/docs`, and the API test
suite is green against in-memory/file SQLite with **no MySQL or network** required.

---

## 2. Directory map (new in Part 2)

```
.
├── requirements.txt              + fastapi, uvicorn[standard]
├── requirements-dev.txt          NEW — dev/test deps (pytest)
├── pytest.ini                    NEW — test discovery + pythonpath
├── docker/
│   └── backend.Dockerfile        NEW — multi-stage, non-root, healthcheck
├── app/
│   ├── schemas/
│   │   └── schemas.py            NEW — Pydantic response models + enums
│   ├── repository/
│   │   ├── papers.py             NEW — paper detail / search / graph queries
│   │   ├── countries.py          NEW — fields list + country ranking + ratios
│   │   └── live.py               NEW — on-demand OpenAlex "cited by" augmentation
│   └── api/
│       ├── deps.py               NEW — FastAPI DB-session dependency
│       ├── cache.py              NEW — small in-process TTL cache
│       ├── main.py               NEW — FastAPI app, health, error handlers
│       └── routers/
│           ├── papers.py         NEW — /api/papers/search, /api/papers/{id}
│           ├── graph.py          NEW — /api/papers/{id}/graph
│           ├── fields.py         NEW — /api/fields
│           └── countries.py      NEW — /api/fields|domains/{id}/country-ranking
└── tests/                        NEW — SQLite TestClient API tests + unit tests
    ├── conftest.py               seeded SQLite fixture + TestClient
    ├── test_api_health_fields.py
    ├── test_api_papers.py
    ├── test_api_graph.py
    ├── test_api_countries.py
    └── test_ratios.py
```

Reused unchanged from Part 1: `app/config.py`, `app/logging_config.py`,
`app/db/{models,database}.py`, `app/processing/transform.py`,
`app/ingestion/openalex_client.py`.

---

## 3. File-by-file reference

### Schemas (`app/schemas/schemas.py`)

All response shapes as Pydantic v2 models, plus two `str` enums used as query
parameters so FastAPI validates them automatically (invalid value → **422**):

- `GraphDirection` = `cites | cited_by`.
- `RankingOrderBy` = `citations | papers | universities | gdp | population |
  papers_per_gdp | papers_per_university | papers_per_capita` (exactly the §8 list).
- `HealthResponse`, `AuthorOut`, `PaperDetail`, `PaperSummary`,
  `GraphFocus / GraphNode / GraphEdge / GraphResponse`,
  `FieldInfo / DomainInfo / FieldsResponse`,
  `TopPaper`, `CountryRankingRow`, `CountryRankingResponse`.

Every router declares one of these as its `response_model`, which is what makes the
OpenAPI/Swagger schema complete and typed.
*Final use:* Part 3's `api_client.py` mirrors these shapes; they are the frozen
contract between API and frontend.

### Repository layer (`app/repository/`)

Pure query functions that take a `Session` and return **plain dicts** (not ORM
objects), so serialization never touches a closed session and the functions are
unit-testable in isolation.

**`papers.py`**
- `paper_detail()` — one paper + its authors (ordered first → middle → last via a
  SQL `CASE`, then by name); returns `None` if the id is unknown (router → 404).
- `search_papers()` — title `ILIKE` substring match, optional `field_id`/`domain_id`
  filters, **only fully-ingested papers** (`ingested=1`, real seeds, never
  enrichment stubs), ordered by `cited_by_count` desc, capped by `limit`.
- `get_graph()` — the citation graph for one focus paper:
  - `direction=cites` → edges where `citing_id = focus`; `total_related =
    referenced_works_count`.
  - `direction=cited_by` → edges where `referenced_id = focus`; `total_related =
    cited_by_count` (the **full** citing-paper count — C4).
  - neighbours are the top-`limit` related papers ordered by `cited_by_count`;
    `shown` = how many were actually drawn; every edge is stored as the directed
    pair `{source: citing, target: referenced}`. Falls back to the live edge count
    when the focus is a stub with no declared total.

**`live.py`**
- `fetch_live_cited_by()` — the `live=true` switch from plan §2.2(6): reuses the
  Part 1 `OpenAlexClient` with `filter=cites:<id>` to pull citing works that are
  **not** in the corpus, returning extra node/edge dicts (never persisted). Network
  failures are caught by the caller so the endpoint degrades to DB-only.

**`countries.py`**
- `list_fields()` — distinct fields (with `paper_count`) and the domains they roll
  up to (with `paper_count`), for the Tab 2 dropdown.
- `field_exists()` / `domain_exists()` — existence checks driving **404s**.
- `country_ranking()` — the Tab 2 workhorse. Aggregates `paper_countries ⋈ papers`
  within a field **or** domain scope, joins `countries` for GDP / population /
  university counts, computes the three productivity ratios, sorts by the chosen
  metric (with `NULL`/missing data sorted **last**), caps to `limit`, then fetches
  the single **most-cited paper per country** for the page in one window-function
  query (`ROW_NUMBER() OVER (PARTITION BY country ORDER BY cited_by_count DESC)`).
- `_ratio_per_100b_gdp` / `_ratio_per_university` / `_ratio_per_million_capita` —
  the ratio math, each guarding against `None`/zero denominators (→ `null`).

### API plumbing (`app/api/`)

**`deps.py`** — `get_db()`, a FastAPI dependency that yields a read-only session
from Part 1's `get_session_factory()` and always closes it. Overridable in tests.

**`cache.py`** — a tiny `TTLCache` (monotonic-clock expiry) plus a registry and
`clear_all_caches()`. Because the dataset is loaded once and is static, the read-
heavy `/api/fields` and country-ranking responses are cached (300 s TTL) keyed on
their scalar parameters only — the request session is used solely to compute a miss,
never stored. Tests clear the registry between cases.

**`main.py`** — builds the `FastAPI` app (title/version/description for Swagger),
adds permissive **CORS** (so the Streamlit app can call it cross-origin), defines
`GET /api/health` (probes the DB with `SELECT 1`), includes the four routers under
the `/api` prefix, and registers a catch-all exception handler that logs via loguru
and returns a clean `500 {"detail": "Internal server error"}`. FastAPI's built-in
handlers still produce `404`/`422` for `HTTPException` and validation errors.

### Routers (`app/api/routers/`)

| File | Endpoint(s) |
|---|---|
| `papers.py` | `GET /api/papers/search`, `GET /api/papers/{paper_id}` (search declared first so it is not shadowed by the id route) |
| `graph.py` | `GET /api/papers/{paper_id}/graph` (`direction`, `limit`, `live`) |
| `fields.py` | `GET /api/fields` (cached) |
| `countries.py` | `GET /api/fields/{field_id}/country-ranking`, `GET /api/domains/{domain_id}/country-ranking` (both cached) |

### Containerization (`docker/backend.Dockerfile`)

Multi-stage build on `python:3.12-slim`: stage 1 installs requirements into a prefix,
stage 2 copies only the installed packages + `app/` + `sql/`, runs as a non-root
`appuser`, exposes `8000`, declares a `HEALTHCHECK` hitting `/api/health`, and starts
uvicorn. *Final use:* Part 3 wires this image into `docker-compose` as the `backend`
service that the frontend reaches at `http://backend:8000`.

### Tests (`tests/`)

`conftest.py` points `DATABASE_URL` at a throwaway SQLite file, resets the Part 1
engine globals, creates the schema from the **same** `Base.metadata`, and seeds a
small deterministic fixture (3 countries incl. one with missing GDP/population, 2
fields/2 domains, 5 papers incl. one stub, authors, country links, citation edges).
The `client` fixture returns a `TestClient` with caches cleared. The suite (27 tests)
covers health, fields/domains counts, search ordering + filters + stub exclusion,
paper detail + author ordering + 404, graph `cites`/`cited_by` totals + caps + edge
direction + stub nodes + `live` augmentation (monkeypatched, no network) + graceful
degradation, country ranking ordering + ratios + null-sorting + top-paper-per-country
+ field/domain 404s, and the ratio math (including divide-by-zero/None).

---

## 4. API contract (the freeze point for Part 3)

| Method & path | Query params | Success | Errors |
|---|---|---|---|
| `GET /api/health` | — | `{status, database}` | — |
| `GET /api/fields` | — | `{fields[], domains[]}` | — |
| `GET /api/papers/search` | `q?`, `field_id?`, `domain_id?`, `limit=20 (1..100)` | `PaperSummary[]` | 422 |
| `GET /api/papers/{id}` | — | `PaperDetail` (incl. `authors[]`, `doi`, `cited_by_count`, OA fields, abstract) | 404 |
| `GET /api/papers/{id}/graph` | `direction=cites\|cited_by`, `limit=50 (1..200)`, `live=false` | `GraphResponse` (`focus`, `nodes[]`, `edges[]`, `total_related`, `shown`, `live`) | 404, 422 |
| `GET /api/fields/{field_id}/country-ranking` | `order_by=papers (enum)`, `limit=30 (1..200)` | `CountryRankingResponse` | 404, 422 |
| `GET /api/domains/{domain_id}/country-ranking` | `order_by=papers (enum)`, `limit=30 (1..200)` | `CountryRankingResponse` | 404, 422 |

`CountryRankingRow`: `country_code`, `country_name`, `paper_count`,
`total_citations`, `num_universities`, `gdp_usd`, `population`, `papers_per_gdp`,
`papers_per_university`, `papers_per_capita`, `top_paper{id,title,cited_by_count,doi}`.

> **Amendment (Part 3):** the two ratio fields were renamed from
> `papers_per_100b_gdp` / `papers_per_million_capita` to **`papers_per_gdp` /
> `papers_per_capita`** so they match the `order_by` enum values exactly — the
> frontend then needs no enum↔field mapping. The ratio **math is unchanged**
> (still papers per 100B USD GDP and per million capita); only the response field
> names changed. The internal helpers keep their descriptive names
> (`_ratio_per_100b_gdp`, `_ratio_per_million_capita`). CLAUDE.md §8's JSON
> example still shows the old names; the code and this contract are the
> authoritative source. See [part3.md](part3.md) §2.

---

## 5. Plan review — inconsistencies found & how they were resolved

Part 1 was reviewed and is internally consistent; the API was coded against its
actual schema (`app/db/models.py`) and helpers (`short_id`, session factory,
`OpenAlexClient`). The following **Part 2 plan ambiguities** were resolved with
sensible, additive defaults (no schema or §8 contract was broken):

| # | Issue in the plan | Resolution |
|---|---|---|
| 1 | §8 only defines `country-ranking` under `/api/fields/{field_id}`, but §9 (Tab 2) requires picking a **Field _or_ Domain**. | Added a purely **additive** sibling `GET /api/domains/{domain_id}/country-ranking` with the identical response shape. The frozen §8 field endpoint is unchanged; `scope_type` in the response says which was used. |
| 2 | The `order_by` enum uses `papers_per_gdp` / `papers_per_capita`, but the JSON example names the fields `papers_per_100b_gdp` / `papers_per_million_capita`. | **Resolved in Part 3:** the response fields were **renamed to match the enum** (`papers_per_gdp` / `papers_per_capita`), removing the mapping entirely. The ratio math is unchanged; only the field names changed (units now documented, not encoded in the name). See the amendment note in §4 and [part3.md](part3.md) §2. |
| 3 | OpenAlex ids are URLs but Part 1 stores the short form (`fields/22 → "22"`). | Path params (`field_id`, `domain_id`, `paper_id`) use the **short stored form**, consistent with `transform.short_id()`. |
| 4 | "is cited by" live switch (§2.2.6) is only meaningful where the corpus is incomplete. | `live=true` augments **`cited_by`** only (via `cites:<id>`); `cites` is served from the authoritative DB edge list. Live failures degrade gracefully to DB-only. |
| 5 | Author display order: `paper_authors` stores only a position label, not an ordinal. | Order **first → middle → last** via SQL `CASE`, then by display name. |
| 6 | Ranking with missing GDP / population / university data. | Ratios return `null` and such rows sort **last**; `total_citations` coalesces to 0. |

Open follow-ups for Part 3 (not blocking): the `live` network path is exercised in
tests only via monkeypatch; real end-to-end `live=true` needs `OPENALEX_EMAIL` set
and is best demoed against the loaded MySQL dataset.

---

## 6. How to check the code right now

### Prerequisites
- The Part 1 `.venv` (this repo was built/tested on Python 3.12+).
- No MySQL or network needed for the test suite.

### Step 1 — install the new dependencies
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Step 2 — run the test suite (SQLite, fully offline)
```powershell
.\.venv\Scripts\python.exe -m pytest
```
Expect **27 passed**. This proves every endpoint returns correct typed JSON and the
ratio math is correct, with no MySQL and no network.

### Step 3 — byte-compile everything (optional)
```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests scripts
```

### Step 4 — run the live API against the Part 1 MySQL data
```powershell
docker compose up -d mysql      # from Part 1
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000
```
Then browse:
- Swagger UI: <http://localhost:8000/docs>
- Health:     <http://localhost:8000/api/health>
- Fields:     <http://localhost:8000/api/fields>
- Search:     <http://localhost:8000/api/papers/search?q=learning&limit=10>
- Detail:     `http://localhost:8000/api/papers/<W…>`
- Graph:      `http://localhost:8000/api/papers/<W…>/graph?direction=cited_by&limit=50`
- Ranking:    `http://localhost:8000/api/fields/<field_id>/country-ranking?order_by=papers_per_gdp`

(If you ran only the Part 1 smoke ingestion, `--max-papers 200`, the corpus is small
but every endpoint still responds; rankings are richer after a larger load.)

### Step 5 — build the backend image (optional)
```powershell
docker build -f docker/backend.Dockerfile -t paper-explorer-backend .
```

---

## 7. Handoff to Part 3

Part 3 (frontend / integration) consumes this contract:
- `api_client.py` calls only these endpoints (the frontend never touches MySQL).
- Tab 1 uses `search` → `papers/{id}` (right panel: DOI, cited-by, OA badge, authors,
  abstract) → `papers/{id}/graph` (header "Cited by N — showing top {shown}").
- Tab 2 uses `fields` → `fields/{id}/country-ranking` **or**
  `domains/{id}/country-ranking`, with the ratio sort metrics for "above-weight"
  countries.
- The `backend.Dockerfile` becomes the `backend` compose service; dev/test/prod
  overrides and the `locust` performance tests are added in Part 3.
