# Part 1 — Data Foundation & Ingestion

This document describes every file created for **Part 1** of the Paper Citation
Explorer (see [CLAUDE.md](CLAUDE.md) for the overall plan), what each file does,
and how it will be used by the later parts (Part 2 = FastAPI backend, Part 3 =
Streamlit frontend + delivery). The last section explains how to verify the code
right now.

---

## 1. What Part 1 delivers

Part 1 is the **data owner**: it stands up MySQL, defines the schema, talks to
the three open-data sources, normalises their payloads, and runs a one-time,
size-monitored pipeline that fills the database. After Part 1 the database holds
papers, authors, institutions, the citation edge list, and country reference
data — everything Part 2's API will query.

It maps onto the bottom four layers of the architecture:

```
Open-data sources  → ingestion (clients) → processing (transform) → storage (MySQL)
                                                                      ▲
                                          one-time pipeline (CLI) ────┘
```

The backend (Part 2) and frontend (Part 3) sit on top of the same MySQL schema
and never re-implement ingestion — they read what this pipeline wrote.

---

## 2. Directory map

```
.
├── docker-compose.yml          MySQL service + named volume + init SQL mount
├── requirements.txt            Python runtime dependencies
├── .env / .env.example         secrets & connection settings (.env is git-ignored)
├── .gitignore / .dockerignore  ignore rules
├── sql/
│   └── 001_schema.sql          raw DDL, run once on first container boot
├── scripts/
│   └── run_pipeline.py         CLI entry point for the pipeline
└── app/
    ├── config.py               typed settings (pydantic-settings)
    ├── logging_config.py       loguru setup (stderr + rotating file)
    ├── db/
    │   ├── models.py           SQLAlchemy ORM models (mirror of the SQL schema)
    │   ├── database.py         engine / session factory / size query
    │   └── upsert.py           dialect-aware bulk upsert / insert helpers
    ├── ingestion/
    │   ├── _http.py            shared GET-with-retry helper
    │   ├── openalex_client.py  OpenAlex client (cursor paging, polite pool)
    │   ├── universities_client.py  hipolabs universities client
    │   ├── worldbank_client.py World Bank countries/GDP/population client
    │   └── abstract.py         decode OpenAlex inverted-index abstracts
    ├── processing/
    │   └── transform.py        raw payloads → normalised DB-ready row dicts
    └── pipeline/
        └── populate.py         the 5-phase, size-monitored population pipeline
```

---

## 3. File-by-file reference

### Infrastructure & configuration

**`docker-compose.yml`**
Defines the `mysql` service (MySQL 8, utf8mb4, a 512 MB buffer pool, `max-allowed-packet=64M`
for large batch transactions), a named volume `papers_mysql_data`, a healthcheck,
and mounts `./sql` into `/docker-entrypoint-initdb.d` so the schema is applied on
first boot. The host port is `${MYSQL_PORT:-3306}`.
*Final use:* Part 3 extends this same file with `backend` and `frontend` services
that reach MySQL by the service name `mysql:3306`; dev/test/prod overrides build on it.

**`sql/001_schema.sql`**
The authoritative DDL: 11 tables (InnoDB, utf8mb4), all indexes, and the foreign
keys for the link tables. Runs **once**, automatically, when the data volume is
empty. `init_db()` (`create_all`) is the parity net for environments that don't
use the container init.
*Final use:* the contract Part 2 codes against; the documented schema in `docs/DATABASE.md`.

**`requirements.txt`**
Runtime deps only: SQLAlchemy, PyMySQL (+ cryptography for MySQL 8's
`caching_sha2_password` auth), httpx, tenacity, loguru, pydantic, pydantic-settings.
*Final use:* Part 2/3 add their own deps (FastAPI, Streamlit, pytest, locust).

**`.env` / `.env.example`**
`.env` holds the real OpenAlex email + key and the MySQL credentials; it is
git-ignored and never committed. `.env.example` is the committed template.
Both are loaded by `config.py` (for the app) and by `docker compose` (for the
container) — which is why the MySQL vars use the plain `KEY=value` form.
*Final use:* the single source of config for every service in every environment.

**`.gitignore` / `.dockerignore`**
Keep `.env`, `.venv`, `__pycache__`, `logs/`, etc. out of git and out of the
Docker build context.

### Application core

**`app/config.py`**
A pydantic-settings `Settings` class: OpenAlex (email/key/base URL), the World
Bank & hipolabs base URLs, MySQL connection parts, HTTP timeout/retry/backoff,
logging, and `target_gb`. `sqlalchemy_url` builds the `mysql+pymysql://…` URL (or
honours a `DATABASE_URL` override, e.g. SQLite for tests); `safe_sqlalchemy_url`
redacts the password for logging. `get_settings()` is an `lru_cache` singleton.
*Final use:* every layer (API, pipeline, tests) imports `get_settings()` — secrets
are read here once and never appear as literals or in logs.

**`app/logging_config.py`**
`configure_logging()` sets up loguru once: a stderr sink (Docker/Loki-friendly)
plus a rotating, compressed file sink at `logs/ingest.log`. Idempotent.
*Final use:* the backend calls the same function so all layers share one log format.

### Storage layer (`app/db/`)

**`app/db/models.py`**
SQLAlchemy 2.0 ORM models, one per table, matching `001_schema.sql` exactly. Uses
type variants so the same models work on MySQL and SQLite (`abstract` is
MEDIUMTEXT on MySQL / TEXT elsewhere; `BigIntType` is BIGINT on MySQL). Exposes
`Base` for `create_all`.
*Final use:* Part 2's repository/query layer selects through these models; the
test suite builds an in-memory SQLite DB from the same `Base.metadata`.

**`app/db/database.py`**
Lazily creates the engine (connection pool, `pool_pre_ping`) and a `sessionmaker`.
Provides `get_engine()`, `get_session_factory()`, a `session_scope()`
context manager, `init_db()` (create-all parity net), and `get_db_size_bytes()`
(reads `information_schema` on MySQL / `PRAGMA` on SQLite) — the latter is what
makes the load **size-monitored**.
*Final use:* the API opens sessions the same way (via a FastAPI dependency in Part 2).

**`app/db/upsert.py`**
`bulk_upsert()` and `bulk_insert()` — chunked, dialect-aware writes. On MySQL it
emits `INSERT … ON DUPLICATE KEY UPDATE`; on SQLite `INSERT … ON CONFLICT`.
`update_cols=None` means *do nothing on conflict* (used for link tables and stub
papers so they never clobber real rows). This is what makes every write
**idempotent**, so the pipeline is safely re-runnable.
*Final use:* primarily a pipeline concern; available to any future writer.

### Ingestion layer (`app/ingestion/`)

**`app/ingestion/_http.py`**
`get_json()` — a shared httpx GET wrapped in a tenacity retry (exponential
backoff on 429/5xx and transport/timeout errors). Used by the two simpler clients.

**`app/ingestion/openalex_client.py`**
`OpenAlexClient`: identifies via `mailto` (polite pool) and an optional premium
`api_key`. `iter_works()` streams works via cursor paging (`cursor=*` →
`meta.next_cursor`), most-cited first, with an optional `filter` and `max_records`
cap. `fetch_works_by_ids()` batch-fetches up to 50 works by short id
(`ids.openalex:W1|W2|…`) for enrichment. Has its own tenacity retryer and a
context-manager lifecycle.
*Final use:* the live "cited by" augmentation in Part 2 reuses the same client /
filter pattern (`cites:<id>`).

**`app/ingestion/universities_client.py`**
`UniversitiesClient.fetch_all()` pulls the full hipolabs `/search` dump (~10k
records) in one request. HTTP-only source; treated as best-effort.

**`app/ingestion/worldbank_client.py`**
`WorldBankClient`: `get_countries()` (ISO-3, ISO-2, name; aggregates skipped),
and `get_gdp()` / `get_population()` which return `ISO-3 → (value, year)` using
`mrnev=1` (most recent non-empty value). `_fetch_pages()` handles the World Bank
`[meta, data]` envelope and pagination.
> **Note (was an inline comment):** indicator requests use `per_page=1000`, not
> `20000`. With `per_page=20000` **and** `page=1`, the World Bank API
> intermittently returns `400` for some indicators (it did for `SP.POP.TOTL`);
> `1000` is safe and the result set (~265 rows) still fits one page.

*Final use:* country GDP / population / university counts power Tab 2's
productivity ratios (papers per GDP, per university, per capita).

**`app/ingestion/abstract.py`**
`decode_abstract()` rebuilds abstract text from OpenAlex's
`abstract_inverted_index` (`{word: [positions]}`); handles `null`.
*Final use:* the abstract shown in the API paper-detail / right panel.

### Processing layer (`app/processing/transform.py`)

The normalisation/integration concern. Key functions:
- `short_id()` — strip the OpenAlex URL prefix (`…/W123` → `W123`, `…/fields/31` → `31`).
- `decode`/clip helpers — `_clip()` truncates over-length strings to column widths
  (MySQL runs strict mode, so this prevents "Data too long" crashes mid-load).
- `parse_work()` — turn one full OpenAlex work into a `ParsedWork`: the paper row,
  deduped authors/institutions, the `paper_authors`/`paper_institutions` links, the
  **derived country set**, **`is_educational`** (any affiliated institution of type
  `education`), the field/domain row, and the normalised `referenced_works` ids.
- `parse_stub()` — a lightweight paper row (`ingested=False`) for enrichment.
- `parse_universities()` / `build_country_rows()` — Phase-1 reference data:
  aggregate universities per ISO-2 and reconcile World Bank ISO-3 indicators to the
  canonical ISO-2 key, merging GDP, population and university counts.
*Final use:* pure functions, unit-tested directly in Part 2's test suite.

### Pipeline (`app/pipeline/populate.py`)

`run_pipeline(PipelineConfig)` orchestrates five phases:
- **Phase 0 – schema:** `init_db()` ensures tables exist.
- **Phase 1 – reference data:** load universities (truncate-and-reload) and World
  Bank countries/GDP/population. Each source call is independently wrapped, so one
  failure degrades gracefully instead of wiping the rest.
- **Phase 2 – corpus:** stream most-cited works, parse them, and write each batch
  in FK-safe order via `_write_batch()` (parents → country/paper stubs → link
  rows). After every batch it measures DB size and **stops near `--target-gb`**.
- **Phase 3 – enrichment:** find referenced "stub" papers (no title yet), batch-
  fetch their title + citation count so graph nodes are labelled (capped by
  `--max-enrichment-ids`).
- **Phase 4 – finalize:** write an `ingest_runs` audit row and return a summary.

`_write_batch()` is the heart: it dedupes rows, **stubs every referenced paper and
unknown country before inserting the links that point at them** (so foreign keys
always hold), and commits per batch (resumable). `scope_to_filter()` maps
`--scope popular|field:ID|domain:ID` to an OpenAlex filter.
*Final use:* run once to build the dataset; not called by the API.

### CLI (`scripts/run_pipeline.py`)

Argparse wrapper around `run_pipeline()`. Flags: `--scope`, `--target-gb`,
`--max-papers` (smoke cap), `--max-enrichment-ids` (0 disables Phase 3),
`--batch-size`, `--skip-reference-data`, `--skip-enrichment`. Prints the JSON
summary and exits non-zero on failure.
*Final use:* the documented one-liner to (re)build the database.

---

## 4. Schema at a glance

| Table | Purpose |
|---|---|
| `papers` | one row per work; `ingested=1` full, `0` = enrichment stub |
| `authors`, `institutions` | shared entities |
| `paper_authors`, `paper_institutions` | M:N links |
| `paper_countries` | derived M:N (paper → every author-institution country) |
| `paper_references` | directed citation edge list (`citing_id` → `referenced_id`) |
| `countries` | ISO-2 key + GDP + population + university count |
| `universities` | hipolabs dump |
| `fields` | OpenAlex field/domain seen in the corpus (Tab 2 dropdown) |
| `ingest_runs` | one audit row per pipeline run |

---

## 5. How to check the code right now

### Prerequisites
- Docker Desktop running
- Python 3.12+ (this repo was built/tested on 3.14)
- `.env` present with a real `OPENALEX_EMAIL` (already set here)

### Step 1 — MySQL is up
```powershell
docker compose up -d mysql
docker ps --filter name=papers-mysql --format "{{.Names}}: {{.Status}}"
```
Expect `papers-mysql: Up … (healthy)`.

### Step 2 — Python environment
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Step 3 — Run a smoke ingestion (minutes)
```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --scope popular --max-papers 200 --max-enrichment-ids 200
```
A successful run ends with JSON like:
```json
{ "scope": "popular", "papers_ingested": 200, "enriched": 194,
  "db_size_bytes": 6602752, "db_size_gb": 0.006, "status": "success" }
```

### Step 4 — Inspect the data (MySQL CLI inside the container)
```powershell
docker compose exec mysql mysql -upapers -ppaperspass papers -e "SELECT (SELECT COUNT(*) FROM papers) AS papers, (SELECT COUNT(*) FROM papers WHERE ingested=1) AS ingested, (SELECT COUNT(*) FROM authors) AS authors, (SELECT COUNT(*) FROM institutions) AS institutions, (SELECT COUNT(*) FROM paper_references) AS edges, (SELECT COUNT(*) FROM countries) AS countries, (SELECT COUNT(*) FROM universities) AS universities;"
```
Foreign-key integrity (every edge points at a real paper row — expect `0`):
```powershell
docker compose exec mysql mysql -upapers -ppaperspass papers -e "SELECT COUNT(*) AS orphan_edges FROM paper_references r LEFT JOIN papers p ON p.id=r.referenced_id WHERE p.id IS NULL;"
```
A Tab-2-style country ranking preview:
```powershell
docker compose exec mysql mysql -upapers -ppaperspass papers -e "SELECT pc.country_code, c.name, COUNT(*) AS papers, c.gdp_usd, c.num_universities FROM paper_countries pc LEFT JOIN countries c ON c.code=pc.country_code GROUP BY pc.country_code, c.name, c.gdp_usd, c.num_universities ORDER BY papers DESC LIMIT 8;"
```
The audit trail:
```powershell
docker compose exec mysql mysql -upapers -ppaperspass papers -e "SELECT id, scope, status, papers_ingested, db_size_bytes, message FROM ingest_runs ORDER BY id DESC;"
```

### Step 5 — Confirm idempotency
Run Step 3 again. `papers_ingested` stays the same and no duplicate rows appear
(all writes are upserts) — only `ingest_runs` gains a new row.

### Optional — run only part of the pipeline
```powershell
# corpus only (reference data already loaded), no enrichment:
.\.venv\Scripts\python.exe scripts\run_pipeline.py --scope popular --max-papers 50 --skip-reference-data --skip-enrichment
```

### Optional — byte-compile everything
```powershell
.\.venv\Scripts\python.exe -m compileall -q app scripts
```

When you're ready for the real dataset, drop the caps:
```powershell
.\.venv\Scripts\python.exe scripts\run_pipeline.py --scope popular --target-gb 5
```
