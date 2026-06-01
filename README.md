# Paper Citation Explorer

A layered data system that ingests scholarly metadata from three open-data
sources (**OpenAlex**, **World Bank**, **universities.hipolabs**), stores it in
**MySQL**, exposes it through a **FastAPI** REST API, and presents it in a
**Streamlit** frontend with two views:

1. **Citation graph** — pick a paper, toggle *cites* / *is cited by*, explore an
   interactive node-link graph, click a node for a detail panel (DOI, cited-by
   count, abstract, open-access badge).
2. **Country analytics** — pick an OpenAlex field or domain and rank countries,
   including productivity ratios (papers per GDP / per university / per capita)
   that surface countries punching above their economic or institutional weight.

The architecture is a closed, top-down layered system — the frontend talks only
to the backend, which is the only service (besides the one-time pipeline) that
touches the database.

```
sources → ingestion → processing → MySQL → FastAPI → Streamlit
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (C4 + UML),
[docs/DATABASE.md](docs/DATABASE.md), [docs/API.md](docs/API.md),
[docs/TECH_CHOICES.md](docs/TECH_CHOICES.md), and the build journals
[part1.md](part1.md), [part2.md](part2.md), [part2_5.md](part2_5.md),
[part3.md](part3.md).

---

## Quick start (Docker, all three services)

```bash
cp .env.example .env          # set OPENALEX_EMAIL (polite pool); defaults are fine for local
docker compose up -d          # mysql + backend + frontend
```

If the database volume is empty, run the one-time population pipeline:

```bash
docker compose exec backend python scripts/run_pipeline.py --scope popular --target-gb 1
```

(or, on Windows, the end-to-end helper `scripts/run_full_pipeline.ps1 -TargetGb 1`).

Then open:
- **Frontend (UI):** http://localhost:8501
- **API docs (Swagger):** http://localhost:8000/docs
- **Health:** http://localhost:8000/api/health

---

## Local development (without containers)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-frontend.txt

docker compose up -d mysql                                      # database only
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000

$env:API_BASE_URL = "http://localhost:8000"
.\.venv\Scripts\python.exe -m streamlit run app/frontend/streamlit_app.py
```

The frontend reads `API_BASE_URL` (default `http://localhost:8000`).

---

## Environments (compose overrides)

```bash
# dev: hot reload + source bind-mounts
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# test: run the pytest suite in a container (SQLite, no MySQL/network)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests

# prod: restart=always, uvicorn workers, no reload
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q                 # unit + API + performance
locust -f tests/locustfile.py --host http://localhost:8000   # load test (running API)
```

- **Unit / API** — offline against in-memory SQLite seeded with fixtures.
- **Performance** — `tests/test_performance.py` asserts hot endpoints respond
  under a threshold; `tests/locustfile.py` drives load against a running API.

---

## Configuration & secrets

All configuration is environment-driven via `pydantic-settings`. Secrets live in
a git-ignored `.env` (template: `.env.example`), are injected into containers by
Compose, and are never hardcoded, committed, or logged. No API keys are required
for the public sources; set `OPENALEX_EMAIL` to join OpenAlex's polite pool.

---

## 10-minute demo script

1. **Setup (1 min).** `docker compose up -d`; show all three containers healthy
   (`docker compose ps`). Open the UI (`:8501`) and Swagger (`:8000/docs`).
2. **Architecture (2 min).** Walk the layered diagram in
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): sources → ingestion → processing
   → MySQL → API → frontend; stress that the frontend only calls the backend.
3. **Tab 1 — citation graph (3 min).** Search a popular paper (e.g. "deep
   learning"). Toggle *cites* vs *is cited by*; point out the header
   "Cited by N papers — showing top 50" (full count vs drawn nodes). Click a node
   → the right panel shows title, authors, DOI link, cited-by count, abstract and
   the open-access badge.
4. **Tab 2 — country analytics (2 min).** Pick a field or domain; rank by
   *papers*, then by *papers per 100B GDP* and *papers per university* to surface
   above-weight countries. Show the table (with per-country top paper link) and
   the bar chart.
5. **Quality (2 min).** Run `pytest -q` (unit + API + perf green); open Swagger to
   show the typed contract; mention loguru logging, retries/backoff, and the
   idempotent size-monitored pipeline.
