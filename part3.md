# Part 3 — Streamlit Frontend, Integration & Delivery

This document describes every file created or changed for **Part 3** of the Paper
Citation Explorer (see [CLAUDE.md](CLAUDE.md) for the overall plan,
[part1.md](part1.md) for the data foundation, [part2.md](part2.md) for the API,
and [part2_5.md](part2_5.md) for the operational hardening + first real load),
what each file does and why. The code itself is comment-free by design — this
file is where the "what and why" lives. The last section explains how to run and
verify the whole app.

---

## 1. What Part 3 delivers

Part 3 is the **frontend / integration / delivery owner**: the top layer of the
architecture plus the wrap that makes the system runnable and presentable.

```
storage (MySQL) → backend API (FastAPI) → frontend (Streamlit)   ← Part 3 adds this layer
                                          + Docker Compose stack (mysql+backend+frontend)
                                          + dev/test/prod overrides
                                          + performance tests
                                          + documentation set
```

The frontend obeys the closed layered architecture: it talks **only** to the
backend over HTTP (never to MySQL). It consumes the frozen Part 2 contract.

**Done-when (met):** `docker compose up` brings up MySQL + backend + frontend and
both tabs work end-to-end against the loaded data; the test suite (now including
performance asserts) is green.

---

## 2. Part 2 amendment — ratio field rename (prerequisite)

Before building the frontend, the Tab 2 ranking response fields were realigned to
the `order_by` query enum so the frontend needs **no** mapping between the two.

| Before (field) | After (field) | Matches enum value |
|---|---|---|
| `papers_per_100b_gdp` | **`papers_per_gdp`** | `papers_per_gdp` |
| `papers_per_university` | `papers_per_university` (unchanged) | `papers_per_university` |
| `papers_per_million_capita` | **`papers_per_capita`** | `papers_per_capita` |

The **ratio math is unchanged** — `papers_per_gdp` is still papers per 100 billion
USD GDP and `papers_per_capita` is still papers per million capita; only the
output field names changed (the units are now documented in [docs/API.md](docs/API.md)
and [docs/DATABASE.md](docs/DATABASE.md) rather than encoded in the name).

Files touched:
- [app/schemas/schemas.py](app/schemas/schemas.py) — `CountryRankingRow` field names.
- [app/repository/countries.py](app/repository/countries.py) — output dict keys in
  `_build_row()` and the `_SORT_KEYS` lambdas. The internal helpers
  `_ratio_per_100b_gdp` / `_ratio_per_million_capita` keep their descriptive names
  (they are imported by `tests/test_ratios.py` and accurately describe the math).
- [tests/test_api_countries.py](tests/test_api_countries.py) — two assertions.
- [part2.md](part2.md) §4 and §5 #2 — documented the change.

`pytest` stayed green through the rename (27 → still 27 + the new perf tests).

---

## 3. Directory map (new / changed in Part 3)

```
.
├── app/frontend/
│   ├── streamlit_app.py        entry point: page config, sidebar health, two tabs
│   ├── api_client.py           the only backend-facing module (requests + st.cache_data)
│   ├── graph_tab.py            Tab 1 — citation graph + node-click detail panel
│   └── analytics_tab.py        Tab 2 — country ranking table + bar chart
├── docker/
│   └── frontend.Dockerfile     NEW — multi-stage, non-root, healthcheck, streamlit
├── docker-compose.yml          CHANGED — added backend + frontend services
├── docker-compose.dev.yml      NEW — hot reload + source bind-mounts
├── docker-compose.test.yml     NEW — pytest in a container (SQLite)
├── docker-compose.prod.yml     NEW — restart=always, uvicorn workers
├── requirements-frontend.txt   NEW — streamlit, streamlit-agraph, requests, pandas
├── requirements-dev.txt        CHANGED — added locust
├── .env.example                CHANGED — added API_BASE_URL
├── tests/
│   ├── test_performance.py     NEW — timing asserts on hot endpoints
│   └── locustfile.py           NEW — load test against a running API
├── docs/
│   ├── ARCHITECTURE.md         NEW — C4 (context/container/component) + UML deployment
│   ├── DATABASE.md             NEW — ER diagram + table/index reference
│   ├── TECH_CHOICES.md         NEW — stack justification
│   └── API.md                  NEW — REST contract reference
├── README.md                   CHANGED — full overview, setup, environments, demo script
└── app/schemas, app/repository, tests  CHANGED — see §2
```

---

## 4. File-by-file reference

### Frontend (`app/frontend/`)

The modules are **flat siblings**, not a Python package. Streamlit runs
`streamlit run app/frontend/streamlit_app.py` and puts that script's directory on
`sys.path[0]`, so the modules import each other as `import api_client` /
`import graph_tab` (not `from app.frontend...`). This avoids any packaging step
and keeps the frontend independent of the backend's import root.

**`api_client.py`** — the single integration boundary. A module of plain functions
over `requests`:
- `API_BASE_URL` is read from the environment (default `http://localhost:8000`;
  set to `http://backend:8000` inside Compose). The frontend never sees MySQL.
- `_get(path, params)` centralises URL building, a 30 s timeout, and error
  translation: a 404 or any ≥400 / transport failure becomes an `ApiError` with a
  human-readable message, which each tab surfaces via `st.error` instead of a raw
  traceback.
- Functions: `get_health`, `get_fields`, `search_papers`, `get_paper`,
  `get_paper_graph`, `field_country_ranking`, `domain_country_ranking`.
- Read-heavy/static responses are wrapped with `@st.cache_data(ttl=300)`. The
  dataset is loaded once and static, so caching is safe and layers on top of the
  backend's own TTL cache. `get_paper_graph` is cached unconditionally, since the
  frontend only requests DB-backed results (the backend's `live` switch is not
  called from the UI).

**`streamlit_app.py`** — entry point. Sets wide layout and page title, renders a
top header row that pings `/api/health` (green "API online · database up", red if
unreachable) and shows the backend URL plus a browser-reachable **Swagger /docs**
link (`API_DOCS_URL`, defaulting to `{API_BASE_URL}/docs` and overridden to
`http://localhost:<port>/docs` in Compose so it opens from the host), then opens
two `st.tabs` and delegates to
`graph_tab.render()` / `analytics_tab.render()`.

**`graph_tab.py`** — Tab 1 (citation graph):
- **Seed picker** — `st.text_input` → `search_papers` (empty query returns the most-
  cited papers) → `st.selectbox` labelled `"{title} — cited {N}"`.
- **Controls** — a `cites` / `is cited by` `st.radio` and a "Max nodes" slider
  (10–200, default 50 = the C3 cap). The frontend serves the graph from the
  authoritative DB edge list only; no live-OpenAlex control is exposed in the UI.
- **Layout** — `st.columns([2, 1])`: graph on the left 2/3, detail panel on the
  right 1/3.
- **Header (C4 compliance)** — the focus paper's total `cited_by_count` is shown as
  a distinct field, independent of how many nodes are drawn: `cited_by` →
  "Cited by N papers — showing top {shown}"; `cites` → "References N works —
  showing top {shown}".
- **Graph** — builds `streamlit_agraph` `Node`/`Edge` lists. The focus node is
  larger and red; open-access neighbours are green, others blue. ID-only papers
  (un-enriched reference stubs with no `title`) are drawn grey and carry **no
  label** — their raw OpenAlex id is never shown. Other labels are truncated
  titles rendered in white at a reduced size (`font={"color": "#ffffff", "size":
  10}`). Hovering a node shows its full, untruncated title as a tooltip (the
  `Node.title` field; falls back to the OpenAlex id only for title-less stubs).
  Node size is **relative to the focus paper**: the focus is a fixed
  reference size (28) and each neighbour is sized by the log of its citation ratio
  to the focus (`28 + 8·log10((count+1)/(focus+1))`, clamped to 6–48), so a
  neighbour reads as bigger/smaller than the paper you picked. Hovering a node
  bolds its label — `interaction.hover` on the `Config`
  plus `chosen={"label": True}` on each node (vis-network has no JSON-only way to
  recolour a label on hover, so bold is the native emphasis). Node spacing is
  widened via the vis-network `barnesHut` physics (`gravitationalConstant=-8000`,
  `springLength=180`, `centralGravity=0.1`, `avoidOverlap=0.5`) set directly on
  `config.physics`. `agraph(...)` returns the clicked node id.
- **agraph click persistence (key quirk)** — `agraph()` returns the clicked id only
  on the rerun triggered by that click; any later rerun (changing a widget) returns
  `None`. So the click is stored in `st.session_state["selected_node"]` and the
  panel renders from session state. Selecting a different seed paper resets the
  selection so the panel falls back to the focus paper.
- **Detail panel (C6)** — `get_paper(id)` → title, an open-access badge (green
  "Open Access · {oa_status}" with the `oa_url` link, or grey "Closed"), authors,
  year/field, a "Cited by" metric, the **DOI** as a `doi.org` link, and the
  abstract (truncated) in an expander.
- **Re-rooting (graph navigation)** — when the panel shows a *non-focus* paper
  (i.e. a clicked neighbour), it offers a "Make this the focus" button. Clicking it
  stores the id in `st.session_state["focus_override"]` and `st.rerun()`s; the
  override takes precedence over the search picker when choosing the graph seed, so
  the graph re-roots on that node. Picking a different paper from the search box
  clears the override. (Single-click still just previews in the panel — the
  prebuilt agraph component only reports single-clicks to Python, so double-click
  re-rooting would require patching the vendored JS bundle.)

**`analytics_tab.py`** — Tab 2 (country analytics):
- **Scope** — `get_fields()` → a Field/Domain `st.radio` → a `st.selectbox` of
  names with paper counts (entries with zero papers are filtered out).
- **Metric** — a "Rank by" selectbox over the 8 `order_by` enum values with
  friendly labels, plus a "Countries" limit slider.
- **Ranking** — calls `field_country_ranking` or `domain_country_ranking`, builds a
  pandas `DataFrame`, and renders it with `st.dataframe` (GDP formatted as currency;
  the per-country top paper shown as a `LinkColumn` to its DOI/OpenAlex page).
- **Chart** — `st.bar_chart` of the selected metric by country. After the §2
  amendment the three ratio `order_by` values are usable **directly** as response
  column names; only the five base metrics need a small lookup
  (`citations→total_citations`, `papers→paper_count`, `universities→num_universities`,
  `gdp→gdp_usd`, `population→population`). Null ratios (already sorted last by the
  API) are dropped from the chart.

### Dependencies

**`requirements-frontend.txt`** (new) — `streamlit`, `streamlit-agraph`,
`requests`, `pandas`. Kept separate from the backend requirements so the frontend
image stays small and does not pull FastAPI/SQLAlchemy. Streamlit is pinned below
1.41 because `streamlit-agraph` tracks the older component API; if a newer pairing
is needed, bump both together and re-test the graph render.

**`requirements-dev.txt`** (changed) — added `locust` for the load test.

### Containerization

**`docker/frontend.Dockerfile`** (new) — mirrors the backend image: multi-stage
`python:3.12-slim`, installs `requirements-frontend.txt` into a prefix, copies only
`app/frontend`, runs as non-root `appuser`, exposes `8501`, declares a
`HEALTHCHECK` against Streamlit's `/_stcore/health`, and starts headless Streamlit.

**`docker-compose.yml`** (changed) — the Part 1 file defined only `mysql`; Part 3
adds:
- `backend` — built from `docker/backend.Dockerfile`, `env_file: .env`, with
  `MYSQL_HOST=mysql` overriding `.env`'s `127.0.0.1` so it reaches the DB by service
  name; `depends_on` mysql healthy; port 8000.
- `frontend` — built from `docker/frontend.Dockerfile`, `API_BASE_URL=http://backend:8000`,
  `depends_on` backend; port 8501.

Services discover each other by name on the Compose network — the lecture's
service-discovery point.

**`docker-compose.dev.yml`** (new) — bind-mounts `./app` and runs the backend with
`uvicorn --reload` and the frontend with `--server.runOnSave true` for hot reload.

**`docker-compose.test.yml`** (new) — a `tests` service (plain `python:3.12-slim`,
the repo mounted, `DATABASE_URL` pointing at SQLite) that installs
`requirements-dev.txt` and runs `pytest`. Needs neither MySQL nor network.

**`docker-compose.prod.yml`** (new) — `restart: always`, the backend on
`uvicorn --workers 4` (no reload), no source mounts. Secrets are supplied via the
orchestrator's secret store / `.env` per [CLAUDE.md](CLAUDE.md) §10.

**`.env.example`** (changed) — documents `API_BASE_URL`.

### Performance tests (`tests/`)

**`test_performance.py`** (new) — reuses the seeded SQLite `client` fixture from
`tests/conftest.py` and asserts that health, fields, search, paper detail, graph
(both directions) and both rankings each respond under 0.5 s. Pure pytest, offline,
runs as part of the normal suite.

**`locustfile.py`** (new) — a `locust` `HttpUser` that, on start, pulls some real
paper and field ids, then weights tasks across health/fields/search/graph/ranking
to load-test a running API (`locust -f tests/locustfile.py --host http://localhost:8000`).

### Documentation (`docs/` + root)

- **`docs/ARCHITECTURE.md`** — C4 Context / Container / Component diagrams and a UML
  deployment diagram (all Mermaid), reflecting the real 3-service topology.
- **`docs/DATABASE.md`** — ER diagram, table/column/index reference, derived-data and
  country-reconciliation notes, and the ratio definitions.
- **`docs/TECH_CHOICES.md`** — the per-layer technology justification.
- **`docs/API.md`** — the REST contract: endpoints, query params, response shapes,
  status codes.
- **`README.md`** — project overview, Docker quick start, local dev, the three
  compose environments, how to run tests, configuration/secrets, and a 10-minute
  demo script.

---

## 5. Key design decisions

1. **Frontend never touches MySQL** — only `api_client.py`, only HTTP to the
   backend (closed layered architecture).
2. **agraph click persistence** — the clicked node id is kept in
   `st.session_state` because `agraph()` returns it only on the click rerun.
3. **C4 total-vs-shown** — the focus paper's full `cited_by_count` is displayed as
   its own field, independent of the drawn node cap (`shown`).
4. **DB-only graph** — the frontend requests the graph from the authoritative DB
   edge list only; the backend's `live=true` augmentation still exists but is not
   exposed in the UI.
5. **Ratio fields aligned to the enum** (§2) — no client-side mapping for the three
   ratio metrics; units documented in the docs.
6. **Layered caching** — `st.cache_data` (TTL) on top of the backend's TTL cache,
   safe because the dataset is static after the one-time load.

---

## 6. How to run & verify the whole app

### Offline tests (no MySQL, no network)
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```
Expect all unit + API + performance tests green.

### Local manual run (against the loaded MySQL)
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-frontend.txt
docker compose up -d mysql
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000
# new terminal:
$env:API_BASE_URL = "http://localhost:8000"
.\.venv\Scripts\python.exe -m streamlit run app/frontend/streamlit_app.py
```
Open http://localhost:8501. Tab 1: search → pick a paper → toggle direction →
click a node → check the panel (DOI, cited-by, OA badge). Tab 2: pick a field or
domain → rank by *papers per 100B GDP* → check the table + bar chart.

### Full stack (all three services)
```powershell
docker compose up -d
docker compose ps        # mysql + backend + frontend healthy
```
- UI: http://localhost:8501 · Swagger: http://localhost:8000/docs

If the DB volume is empty, load it once:
```powershell
docker compose exec backend python scripts/run_pipeline.py --scope popular --target-gb 1
# or on Windows: .\scripts\run_full_pipeline.ps1 -TargetGb 1
```

### Environment overrides
```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up           # hot reload
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests   # pytest in a container
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d        # prod
```

### Load test (optional, running API)
```powershell
.\.venv\Scripts\python.exe -m locust -f tests/locustfile.py --host http://localhost:8000
```

---

## 7. Notes & follow-ups

- `streamlit-agraph` is sensitive to the Streamlit major version; the pin in
  `requirements-frontend.txt` keeps the pair compatible. Bump both together if you
  upgrade.
- Real `live=true` end-to-end needs `OPENALEX_EMAIL` set and is best demoed against
  the loaded MySQL (also noted in [part2_5.md](part2_5.md)).
- CLAUDE.md §8's JSON example still shows the old ratio field names; the code,
  [docs/API.md](docs/API.md) and [part2.md](part2.md) are the authoritative contract
  after the §2 rename.
