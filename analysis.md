# Integrity & Code Review — Paper Citation Explorer

**Date:** 2026-05-31
**Scope:** Full read-through of every source file (config, DB, ingestion, processing,
pipeline, API, repositories, frontend, Docker, tests, SQL). No code was changed.
**Verdict:** The app is architecturally sound and the layering matches the plan in
[CLAUDE.md](CLAUDE.md). Most findings below are *risks / polish / drift*, not crashes.
The two things that genuinely need attention before any demo or hand-off are
(1) the large amount of **untracked working-tree code** and (2) a couple of
**unverified OpenAlex filter strings** that the whole ingest depends on.

A caveat on method: I could not execute the test suite in this environment (only
Python 3.14 with no dependencies is installed; the project targets 3.12). Findings
are by inspection, so the "verify" items are genuinely worth running, not rhetorical.

---

## Severity legend

| Tag | Meaning |
|---|---|
| 🔴 **High** | Can break delivery, ingestion, or produce silently wrong data. Fix before relying on it. |
| 🟠 **Medium** | Real risk under realistic conditions; fine for a demo, fix before "production". |
| 🟡 **Low** | Polish, redundancy, or theoretical edge case. Often fine to leave. |
| 🟢 **OK as-is** | Looks like a smell but is a justified trade-off — documented here so nobody "fixes" it by mistake. |

---

## 1. 🔴 High-impact findings

### 1.1 Most of the application is untracked in git
`git ls-files` shows that the **entire frontend** ([app/frontend/](app/frontend/)),
**all three compose overrides** (`docker-compose.dev/test/prod.yml`), the **frontend
Dockerfile**, [requirements-frontend.txt](requirements-frontend.txt), the whole
[docs/](docs/) folder, [sql/002_grant_process.sql](sql/002_grant_process.sql), the
performance tests, and the locustfile are **untracked**. Several tracked files
(`README.md`, `app/db/database.py`, `app/repository/countries.py`, `app/schemas/schemas.py`,
`tests/test_api_countries.py`, …) are also **modified but unstaged**.

- **Why it's a problem:** a fresh `git clone` would not contain the UI, the test
  override, or the docs. `docker compose -f docker-compose.yml -f docker-compose.test.yml …`
  (the command the README and CLAUDE.md tell graders to run) would fail with
  "no such file". A teammate or CI checking out `main` gets a backend with no
  frontend. The plan explicitly grades on "genuine git history (commit per
  milestone)" — right now two commits hold a partial app and the rest lives only
  on this one disk.
- **When it's OK to leave it:** never, for delivery. The only legitimate reason to
  keep something untracked is genuine secrets ([.env](.env), already ignored) or
  generated artifacts (`logs/`). The frontend and compose files are neither.
- **Fix:** stage and commit the working tree in the milestone-sized commits the
  appendix of CLAUDE.md describes. Confirm `.gitignore` isn't accidentally
  swallowing anything (it isn't — these are just unadded).

### 1.2 Ingestion depends on two OpenAlex filter strings that are not verified
The whole corpus and graph-enrichment flow hinges on filter syntax that nothing in
the code or tests validates against the live API:

1. **Field/domain scope** in [scope_to_filter()](app/pipeline/populate.py#L89-L101)
   builds `primary_topic.field.id:{value}` / `primary_topic.domain.id:{value}`, and
   passes the raw scope value straight through. Stored field ids are the *short*
   form (`"22"`) because [_parse_topic()](app/processing/transform.py#L32-L44) runs
   `short_id()` on the URL. But the docs disagree with themselves about what to
   type: [run_full_pipeline.ps1](scripts/run_full_pipeline.ps1#L3) shows
   `-Scope "field:22"`, while [CLAUDE.md](CLAUDE.md) §11/Appendix and
   [run_pipeline.py](scripts/run_pipeline.py#L21) show `field:fields/22`. Those two
   produce **different filter strings** (`...id:22` vs `...id:fields/22`), and only
   one can be right.
2. **Enrichment** in [fetch_works_by_ids()](app/ingestion/openalex_client.py#L111-L125)
   uses `filter=ids.openalex:W1|W2|...`.

- **Why it's a problem:** if either key/format is wrong, OpenAlex returns an empty
  result set with HTTP 200. The pipeline doesn't treat "0 results" as an error, so
  it would log success while ingesting nothing (field scope) or leaving every graph
  node title-less (enrichment). That is the worst kind of bug: silent.
- **When it's OK to leave it:** the `popular` scope (no filter) is unaffected, so if
  you only ever demo `--scope popular`, the field/domain filter risk doesn't bite.
- **Fix:** run one tiny smoke call for each (`--scope field:22 --max-papers 5`
  and a manual `ids.openalex` fetch), confirm non-empty, and pick **one**
  documented field-id format everywhere. Cheap insurance: have the pipeline log a
  warning when a phase fetches zero records.

---

## 2. 🟠 Medium findings (real risk under realistic use)

### 2.1 Phase 3 enrichment ignores the size target
[ingest_corpus()](app/pipeline/populate.py#L210-L238) checks
`get_db_size_bytes()` after every batch and stops at the target, but
[enrich_references()](app/pipeline/populate.py#L241-L273) then enriches up to
`max_enrichment_ids` (default **50 000**) with **no size check**. The "~5 GB,
size-monitored" guarantee in CLAUDE.md §7 therefore only covers Phase 2.

- **Why it's a problem:** a run that stops Phase 2 right at 5 GB can still add a
  meaningful chunk of stub rows in Phase 3, overshooting the target.
- **When it's OK to leave it:** stubs are small (`STUB_SELECT` has no abstract/edges),
  so overshoot is modest; for a 1–2 GB demo load it's negligible.
- **Fix:** either move the size check into the enrichment loop, or document that the
  effective ceiling is `target + (enrichment stubs)`.

### 2.2 `load_reference_data` can leave `universities` empty on partial failure
In [load_reference_data()](app/pipeline/populate.py#L104-L121) the order inside the
`try` is: fetch → parse → `session.query(University).delete()` → `bulk_insert`. The
`except` only logs a warning. If the **insert** (not the fetch) fails after the
delete, the table has been emptied in the session and is later committed empty by
the `session.commit()` at line 157.

- **Why it's a problem:** a transient DB error during the insert silently wipes the
  university counts, which then feeds `num_universities = 0/None` into every Tab 2
  "papers per university" ratio.
- **When it's OK to leave it:** delete-then-reinsert is the simplest idempotent
  refresh and failure here is rare; for a one-shot local load it's acceptable.
- **Fix:** build the new rows first and only `delete` immediately before a
  guaranteed insert in the same flush, or upsert universities by a natural key
  instead of truncate-and-reload.

### 2.3 Multi-process file logging in prod
[docker-compose.prod.yml](docker-compose.prod.yml) runs uvicorn with `--workers 4`,
and [logging_config.py](app/logging_config.py#L32-L41) adds a rotating **file** sink
(`logs/ingest.log`). Four processes rotating/compressing the same file path is a
classic source of interleaved or lost log lines, even with `enqueue=True` (which only
serialises within a single process).

- **Why it's a problem:** rotation races between processes can corrupt or drop logs —
  exactly when you most want them (under load).
- **When it's OK to leave it:** for the API the stderr sink is the one that matters in
  Docker (captured by the platform); the file sink is mostly for the single-process
  ingestion pipeline. If you ship logs via stdout/stderr to the platform, the file
  sink is redundant in prod anyway.
- **Fix:** make the file sink ingestion-only, or include `{process}` in the filename,
  or drop the file sink when running under multiple workers.

### 2.4 Plan promises Docker secrets in prod; the code uses a plain `.env`
CLAUDE.md §10/§13 and [README.md](README.md#L98-L103) state that production uses
**Docker secrets / a secret store**. The actual [docker-compose.prod.yml](docker-compose.prod.yml)
only sets `restart: always` and worker count; the backend still reads `env_file: .env`
(inherited from [docker-compose.yml](docker-compose.yml#L34)), and the base compose
hard-codes default credentials (`${MYSQL_PASSWORD:-paperspass}`, `:-rootpass`). The
prod override also inherits the **`ports: 3306` mapping**, exposing MySQL on the host.

- **Why it's a problem:** it's a documentation-vs-reality gap that a reviewer reading
  both will catch, and the weak baked-in defaults plus exposed DB port are the kind of
  thing a security rubric item targets.
- **When it's OK to leave it:** for a course mini-project that never runs on a real
  host, the defaults are harmless. But then the *docs should say so* rather than claim
  Docker secrets.
- **Fix:** either implement `secrets:` in the prod override (the plan's own design) or
  soften the README/CLAUDE wording to "prod is configured via env / would use the
  orchestrator's secret store", and drop the `ports` mapping for MySQL in prod.

### 2.5 `container_name` hard-coded on every service
[docker-compose.yml](docker-compose.yml) pins `container_name: papers-*`.

- **Why it's a problem:** you cannot run two stacks side by side, and
  `docker compose up --scale backend=N` fails on the name clash. The prod story
  ("scale out") is implicitly blocked.
- **When it's OK to leave it:** single-stack local dev — fixed names make
  `docker compose exec papers-mysql …` predictable, which the helper script relies on.
- **Fix:** drop `container_name` (compose generates stable names) or only set it in the
  dev override.

---

## 3. 🟡 Redundancy & "doesn't make sense to be separate"

### 3.1 Two parallel HTTP-retry implementations
This is the clearest redundancy in the codebase:

- [app/ingestion/_http.py](app/ingestion/_http.py) defines `RetryableHTTPError`,
  `_RETRYABLE_STATUS`, and a `get_json()` that wraps a `tenacity.Retrying`. It is used
  by [universities_client.py](app/ingestion/universities_client.py) and
  [worldbank_client.py](app/ingestion/worldbank_client.py).
- [openalex_client.py](app/ingestion/openalex_client.py#L25-L82) **re-declares** its
  own `RetryableHTTPError`, its own copy of `_RETRYABLE_STATUS`, and its own inline
  `Retrying` + `_do_get`, instead of using `_http.get_json`.

So the same retry policy and the same constants exist in two places, and
`RetryableHTTPError` is defined twice (the two classes are unrelated types).

- **Why it's a problem:** change the backoff or the retryable status set in one place
  and the other silently diverges. It also makes the layer look like it has two
  "HTTP conventions".
- **When it's OK to leave it:** OpenAlex legitimately needs *cursor paging and a
  persistent client with merged auth params*, which is more than `get_json` offers, so
  a dedicated client class is justified. The duplication is in the **retry plumbing**,
  not the client.
- **Fix:** have `OpenAlexClient` call the shared `get_json` (passing its merged params),
  or extract the `Retrying` factory + status set into `_http` and import it in all
  three clients. Either way, one definition of `RetryableHTTPError`.

### 3.2 Truncation in `_clip` duplicates the DB column lengths
[transform.py](app/processing/transform.py#L8-L11) clips strings to lengths that
mirror the `VARCHAR` sizes in [models.py](app/db/models.py) / [001_schema.sql](sql/001_schema.sql)
(e.g. 255, 512, 1024). If a column length changes, the magic numbers in `_clip` calls
must change too.

- **Verdict 🟢 OK as-is:** this is defensive belt-and-suspenders against MySQL
  "Data too long" errors, and it's cheap. Just be aware the numbers are coupled; a
  comment-free constant table would be the only improvement, and the project
  convention is no inline comments anyway.

### 3.3 Two cache layers
There's a server-side [TTLCache](app/api/cache.py) (fields + rankings) **and**
Streamlit `@st.cache_data(ttl=300)` in [api_client.py](app/frontend/api_client.py).

- **Verdict 🟢 OK as-is:** they sit at different tiers (one saves DB work across all
  clients, the other saves HTTP round-trips for one browser session). Not redundant.
  Worth knowing during a demo: a stale-looking number can be up to ~10 minutes old
  (300 s × 2 layers) right after a reload.

### 3.4 `repository/live.py` is tiny and tightly coupled to the graph router
[live.py](app/repository/live.py) is the only "repository" that makes a network call
and constructs a brand-new `OpenAlexClient` per request.

- **Verdict 🟡 Low:** functionally fine, but it's a "repository" that bypasses the DB
  and ignores the request lifecycle, which is a slight layering smell (a repository is
  meant to be the DB boundary). Acceptable to keep; just don't be surprised that the
  "DB layer" reaches the internet here.

---

## 4. 🟡 Correctness nuances worth documenting (not bugs)

These produce *intended* results, but they're easy to misread, so write them down
before the demo Q&A:

- **`paper_count` is full-counted, not fractional.** A paper authored from NL + US is
  counted once for NL **and** once for US in
  [country_ranking()](app/repository/countries.py#L171-L223). Summing `paper_count`
  across countries exceeds the corpus size. Standard bibliometric "full counting", but
  say so when someone asks why the numbers don't add up.
- **`total_citations` is the *global* citation count, summed.** It uses
  `papers.cited_by_count` (OpenAlex's worldwide count), not intra-corpus edges. So it's
  a popularity proxy, not "citations from within this dataset".
- **Tab 2 only sees papers that have an institution country.** `paper_countries` is
  derived from `authorships[].institutions[].country_code`. Papers with no institution
  metadata silently never appear in any country ranking.
- **Graph "cites" total vs "is cited by" total are different sources.** `cites` uses
  `referenced_works_count` (declared) and `cited_by` uses `cited_by_count` (declared),
  both falling back to the stored edge count. This is correct per CLAUDE.md C4, but the
  two directions are not symmetric and that's deliberate.

---

## 5. 🟡 Things that could be upgraded

| Area | Current | Suggested upgrade | When current is fine |
|---|---|---|---|
| **Dependency pinning** | [requirements.txt](requirements.txt) uses only `>=` lower bounds (except Streamlit, which is capped `<1.41`). | Add upper caps or a lockfile, so a rebuild months later can't pull a breaking major (e.g. a future Pydantic/SQLAlchemy). | For a graded snapshot built once, `>=` is fine; the Streamlit cap already protects the most fragile dep (agraph). |
| **Country ranking sort** | [_sort_and_limit()](app/repository/countries.py#L123-L126) pulls all groups into Python and sorts there. | Push `ORDER BY … LIMIT` into SQL for ratios computed as SQL expressions. | The group set is ≤ ~200 countries, so Python sorting is trivially fast — leave it unless profiling says otherwise. |
| **Top-paper-per-country** | [_top_papers()](app/repository/countries.py#L129-L168) runs a `ROW_NUMBER()` window over all scoped papers for the page's countries. | A correlated `MAX(cited_by_count)` or a lateral join can avoid ranking the full partition. | It's bounded to the page's ≤200 countries and the result is cached 300 s — fine for the data sizes here. |
| **`TTLCache` thread-safety** | [cache.py](app/api/cache.py) uses a plain dict; FastAPI sync endpoints run in a threadpool. | A `threading.Lock` around get/set, or `cachetools`. | Dict ops are GIL-atomic and a rare race only costs a recompute, never corruption — acceptable. |
| **Live cited-by client reuse** | [fetch_live_cited_by()](app/repository/live.py) builds a fresh `OpenAlexClient` (new httpx pool) per request. | Reuse a module-level client. | Live mode is opt-in and occasional; the connection setup cost is irrelevant at that frequency. |
| **CORS** | [main.py](app/api/main.py#L25-L31) allows `*`. | Restrict to the frontend origin in prod. | Read-only public API with no credentials — `*` is harmless here. |
| **Dockerfile healthcheck** | `urllib.request.urlopen(...)` with no timeout. | Pass a `timeout=` so a hung socket can't stall the healthcheck. | Local Docker only; the daemon's own `--timeout=5s` still bounds the check. |
| **`.env` var name** | Code reads `OPENALEX_EMAIL`; CLAUDE.md §10 calls it `OPENALEX_MAILTO`. | Align the doc to the code. | Pure doc drift; the code and `.env.example` agree. |

---

## 6. 🟢 What is genuinely good (don't "fix" these)

So the analysis is balanced — these are correct and intentional:

- **Idempotent upserts everywhere** ([upsert.py](app/db/upsert.py)) with a clean
  MySQL/SQLite dialect split, and `update_cols=None` used precisely so stub inserts
  **never clobber** a fully-ingested paper. The write ordering in
  [_write_batch()](app/pipeline/populate.py#L160-L207) (countries → papers → stubs →
  association/edge tables) respects every FK; bare-code country inserts pre-satisfy the
  `paper_countries` FK. This is the trickiest part of the project and it's done well.
- **MySQL↔SQLite parity** is handled deliberately: `MEDIUMTEXT`/`BIGINT` variants,
  dialect-specific upserts, `get_db_size_bytes` per dialect, window functions supported
  by both. The test suite can run fully offline on SQLite — exactly as the plan intends.
- **Graceful degradation:** live augmentation is wrapped in try/except
  ([graph.py](app/api/routers/graph.py#L38-L39)) and the global handler
  ([main.py](app/api/main.py#L55-L58)) returns a clean 500 without leaking internals.
  Tests `test_graph_live_failure_degrades_gracefully` cover this.
- **Secrets hygiene:** `.env` is ignored, `.env.example` ships placeholders,
  [config.py](app/config.py) exposes `safe_sqlalchemy_url` that masks the password, and
  loguru is configured to not echo it.
- **Test coverage is real:** error paths (404/422), ordering, ratio divide-by-zero
  guards, stub exclusion from search, and the live-mode branch are all asserted.

---

## 7. Suggested order of action

1. **Commit the working tree** (frontend, compose overrides, docs, perf tests) in
   milestone commits — this is the only blocking item. *(§1.1)*
2. **Smoke-test the OpenAlex filters** (`field:` scope + `ids.openalex` enrichment) and
   pick one documented field-id format. Add a "zero results" warning. *(§1.2)*
3. Decide the size-target story for Phase 3 and the prod-secrets story, then make docs
   and code agree on both. *(§2.1, §2.4)*
4. Consolidate the duplicated retry plumbing into [_http.py](app/ingestion/_http.py).
   *(§3.1)*
5. Everything in §5 is optional polish; none of it blocks the demo.

The bottom line: the **code** is in good shape and the architecture holds together; the
**repository state** and a couple of **unverified external contracts** are what put the
project at risk, and both are quick to close out.
