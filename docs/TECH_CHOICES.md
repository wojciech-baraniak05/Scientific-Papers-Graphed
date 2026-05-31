# Technology choices & justification

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | One language across ingestion, API and frontend; required for the course |
| Backend | FastAPI + Uvicorn | REST + JSON, Pydantic validation, **auto OpenAPI/Swagger** at `/docs` (code-first; the spec is generated from typed handlers) |
| ORM / driver | SQLAlchemy 2.0 + PyMySQL | DB-agnostic: MySQL in prod, SQLite in tests from the **same** `Base.metadata` |
| Database | MySQL 8 | Required; relational model fits normalised papers/authors/institutions plus a citation **edge list** |
| Frontend | Streamlit + `streamlit-agraph` | Required frontend; agraph renders an interactive node-link graph and **returns the clicked node id**, which drives the detail panel |
| HTTP client | httpx + tenacity (ingestion), requests (frontend) | Timeouts, retries and exponential backoff against flaky public APIs; the frontend uses the simpler synchronous `requests` |
| Data / charts | pandas + Streamlit native (`st.dataframe`, `st.bar_chart`) | Minimal dependencies; fast tabular + single-metric visualisation for Tab 2 |
| Logging | loguru | Configured once as a crosscutting concern; stderr (Docker/Loki) + rotating file; never logs secrets |
| Config | pydantic-settings | 12-factor: same image, different env vars per environment; secrets come from `.env` / Docker secrets |
| Tests | pytest + locust | Unit + API tests (offline SQLite) and basic load/performance testing |
| Runtime | Docker + Compose | Multi-stage slim images, non-root user, healthchecks, service discovery by name; dev / test / prod overrides |

## Notable decisions

- **Closed layered architecture** — the frontend never touches MySQL; it speaks
  only to the backend over HTTP. Only the backend and the one-time pipeline reach
  the database.
- **Static-data caching** — the dataset is loaded once, so both the backend
  (in-process TTL cache) and the frontend (`st.cache_data`) cache read-heavy
  responses safely.
- **Frontend HTTP client** — `requests` over `httpx` keeps the synchronous
  Streamlit code simple; the frontend image only needs `streamlit`,
  `streamlit-agraph`, `requests`, `pandas`.
- **Ratio field naming** — Tab 2 ratio response fields (`papers_per_gdp`,
  `papers_per_university`, `papers_per_capita`) are named to match the `order_by`
  query enum values, so no client-side mapping is needed.
