# Part 2.5 — Operational hardening & first real data load

This document records the changes made **after** [part2.md](part2.md) (the FastAPI
backend) and **before** Part 3 (the Streamlit frontend). It is not a new
architectural layer — it is the operational work that turned the code into a
running system on a real ~1 GB dataset: a size-monitoring bug fix, a one-command
automation script, the first real database load, and an end-to-end API check
against that data.

See [CLAUDE.md](CLAUDE.md) for the overall plan, [part1.md](part1.md) for the
ingestion foundation, and [part2.md](part2.md) for the API.

---

## 1. Summary of changes

| # | Change | Files |
|---|---|---|
| A | **Size-gauge fix** — the pipeline's "stop at N GB" metric read stale InnoDB stats (~10× low) and would not self-stop. Now reads the real tablespace size. | [app/db/database.py](app/db/database.py), [sql/002_grant_process.sql](sql/002_grant_process.sql) |
| B | **One-command automation** — `run_full_pipeline.ps1` brings up MySQL, grants the privilege the gauge needs, runs the pipeline to a real target size, prints a summary, and optionally starts the API. | [scripts/run_full_pipeline.ps1](scripts/run_full_pipeline.ps1) |
| C | **First real data load (~1 GB)** — popular-scope corpus + reference data, stopped at the real 1 GB boundary, then stub enrichment for graph labels. | (data, `ingest_runs`) |
| D | **API verified against real data** — every Part 2 endpoint exercised on the loaded MySQL, not just SQLite fixtures. | (verification only) |

No new Python dependencies. The API code from Part 2 is unchanged.

---

## 2. Change A — the size-gauge fix

### The bug
Part 1's [`get_db_size_bytes()`](app/db/database.py#L58-L80) summed
`data_length + index_length` from `information_schema.tables`. For InnoDB those
columns come from **cached, approximate statistics** that MySQL 8 only recomputes
when a table changes by ~10% (and querying `information_schema` does **not** refresh
them, because `innodb_stats_on_metadata` is `OFF` by default).

During the first real load this read **~10× low**: at one point the gauge reported
**59 MB** while the tablespaces were really **587 MB** on disk. The pipeline's
Phase-2 stop condition (`size >= target`) therefore would **not** trigger near the
1 GB target — left alone it would have overshot to several GB and could have filled
the disk. The plateaus also lengthened over time (10% of a growing table is more
rows), so the metric sat frozen for dozens of batches.

### The fix
[`get_db_size_bytes()`](app/db/database.py#L58-L80) now, for MySQL, reads the
**real allocated file size** from `information_schema.innodb_tablespaces`
(`file_size`), scoped to the current schema via
`SUBSTRING_INDEX(name,'/',1) = DATABASE()` (which avoids a `LIKE '%'` literal that
PyMySQL would mis-handle). It falls back to the old cached-stats query if the
tablespace view is unavailable, and the SQLite branch is unchanged:

```
MySQL : SUM(file_size) FROM information_schema.innodb_tablespaces  (real, live)
        └─ fallback → SUM(data_length+index_length) FROM information_schema.tables
SQLite: PRAGMA page_count * PRAGMA page_size  (unchanged)
```

### The privilege it needs
`innodb_tablespaces` requires the global **`PROCESS`** privilege, which the app's
`papers` user does not get by default. Two parts:
- [sql/002_grant_process.sql](sql/002_grant_process.sql) grants it on **fresh**
  deploys (init scripts run as root on first container boot, after the schema).
- For already-initialised volumes it is granted once via root (the
  `run_full_pipeline.ps1` script also re-applies it idempotently every run).

**Trade-off:** `PROCESS` is a global privilege (lets the user see other sessions'
queries) — acceptable for this single-app local project, and the fallback means a
missing grant degrades gracefully rather than breaking.

### Verification
- The `papers` app user now reads **1019 MB** (real) instead of 59 MB through the
  same function.
- The API/unit suite is still green — **27 passed** (the SQLite path is untouched).

---

## 3. Change B — `scripts/run_full_pipeline.ps1`

A comment-free PowerShell wrapper that automates the whole "stand it up and fill
it" process, leaning on the fixed gauge so `-TargetGb` now self-stops at the
**real** size (the manual watcher used during the first load is no longer needed).

**Stages (with `Write-Host` banners):**
1. create `.venv` + install `requirements.txt` *only if missing*
2. `docker compose up -d mysql`
3. wait until the `papers-mysql` container is `healthy`
4. ensure the `PROCESS` grant (idempotent — accurate gauge on any volume)
5. run `scripts/run_pipeline.py` (corpus + enrichment + `ingest_runs` audit)
6. print a real-size + row-count summary
7. optional `-StartApi` → launch uvicorn

**Parameters:** `-Scope` (`popular`|`field:ID`|`domain:ID`), `-TargetGb` (1.0),
`-MaxEnrichmentIds` (50000), `-MaxPapers` (-1 = no cap), `-SkipReferenceData`,
`-StartApi`, `-ApiPort` (8000). DB credentials are read from `.env`
(`MYSQL_ROOT_PASSWORD` / `MYSQL_USER` / `MYSQL_DATABASE`) with project defaults.
Decimal `-TargetGb` is formatted with InvariantCulture so non-US locales (comma
decimals) don't break the Python `--target-gb` argument.

**Examples:**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_pipeline.ps1 -TargetGb 2
.\scripts\run_full_pipeline.ps1 -TargetGb 1 -MaxEnrichmentIds 200000 -StartApi
.\scripts\run_full_pipeline.ps1 -Scope "field:22" -MaxPapers 5000
```
Run unsigned scripts via `-ExecutionPolicy Bypass` (or set
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once).

---

## 4. Change C — the first real data load (~1 GB)

Loaded with `run_pipeline.py --scope popular --target-gb 1`. Because the gauge bug
was still present during this load, the run was held to a real 1 GB by polling
`innodb_tablespaces.file_size` externally and stopping the process at ~1019 MB
(the fix in §2 makes this automatic going forward).

**Reference data (Phase 1):** 10,233 universities / 201 countries; 217 World Bank
countries with GDP + population.

**Resulting dataset (current snapshot):**

| metric | value |
|---|---:|
| Real size on disk | ~1.08 GB |
| Total papers | 1,947,958 |
| Fully ingested (abstract, authors, country links) | 48,800 |
| Labelled stub neighbours (enrichment) | 198,661 (~200k target reached) |
| Citation edges | 3,151,017 |
| Authors | 157,085 |
| FK integrity (orphan edges / country links) | 0 |
| Fields represented | 26 (all of them) |

**Stub enrichment.** Phase 3 was run separately (and paused/resumed once) to give
referenced-but-not-seeded papers a title + citation count, so they label and order
correctly as graph neighbours. Enrichment fills existing rows, so it adds little
size (~0.3 MB per 1k labels). It is fully **resumable** — re-running selects only
`ingested=0 AND title IS NULL`, so it never repeats work. During the resume the
OpenAlex client hit a few transient network timeouts and **retried through them via
tenacity** (the resilience the design calls for).

**`ingest_runs`.** A run records its audit row in Phase 4. Loads that are stopped
externally mid-flight (as the size-capped corpus load was) don't write one; a run
that completes normally does. The completed enrichment pass wrote row **id 6**
(`status=success`, `enriched=112553`), and its recorded `db_size_bytes`
(**1.058 GB**) matches the real tablespace size — confirming the §2 gauge fix
end-to-end, since that value now comes from the corrected `get_db_size_bytes()`.

---

## 5. Change D — API verified against the real dataset

The Part 2 API (uvicorn on `127.0.0.1:8000`) was exercised against the loaded MySQL:

```
HEALTH        : {status: ok, database: up}
FIELDS        : 26 fields, 4 domains
SEARCH top3   : W3038568908 (cited 801,217) · "R: A Language…" (352,998) · "Folin…" (318,096)
DETAIL        : authors, cited_by, OA flag, field all populated
GRAPH cites   : total_related=8, shown=5  ·  cited_by total_related=801,217 (in-corpus edges)
RANKING/field (papers_per_gdp) : surfaces above-weight economies (FM, PS, GW, LB…)
RANKING/domain (papers)        : US 5,440 papers · per_100b_gdp 18.9 · per_university 2.3 · top paper + DOI
ERRORS        : 404 unknown paper · 422 bad direction · 404 unknown field
```

Both the field and domain rankings, the productivity ratios, the
top-paper-per-country, and the 404/422 error paths all behave correctly on real
data. (The newest endpoint — the additive `/api/domains/{id}/country-ranking` from
[part2.md](part2.md) §5 — was confirmed live, returning a full ranking payload.)

---

## 6. Files changed / added

| File | Change |
|---|---|
| [app/db/database.py](app/db/database.py) | `get_db_size_bytes()` reads real `innodb_tablespaces.file_size` with cached-stats fallback |
| [sql/002_grant_process.sql](sql/002_grant_process.sql) | **new** — `GRANT PROCESS` so the app user can read the real size on fresh deploys |
| [scripts/run_full_pipeline.ps1](scripts/run_full_pipeline.ps1) | **new** — end-to-end automation (DB up → grant → populate → summary → optional API) |

---

## 7. How to verify now

```powershell
# real on-disk size (the metric the pipeline now stops on)
docker compose exec mysql mysql -uroot -prootpass -e "SELECT ROUND(SUM(file_size)/1024/1024,1) AS real_mb FROM information_schema.innodb_tablespaces WHERE SUBSTRING_INDEX(name,'/',1)='papers';"

# the app reads the same number through the fixed function
.\.venv\Scripts\python.exe -c "from app.db.database import get_session_factory, get_db_size_bytes as g; s=get_session_factory()(); print(round(g(s)/1024/1024,1),'MB'); s.close()"

# test suite still green
.\.venv\Scripts\python.exe -m pytest -q

# API against the live data
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000
#   http://localhost:8000/docs · /api/fields · /api/papers/search?q=learning
```

---

## 8. Follow-ups (optional, not blocking Part 3)

- **Live cited-by:** for hubs like `W3038568908`, `direction=cited_by` shows
  `total_related` in the hundreds of thousands but few in-corpus edges; the
  `live=true` switch fills neighbours from OpenAlex on demand.
- **Deeper enrichment:** more `--max-enrichment-ids` labels more graph neighbours;
  size headroom is large (labels are cheap), the cost is request time.
- **Privilege scope:** if granting global `PROCESS` is undesirable in a stricter
  environment, the gauge silently falls back to cached stats (and the pipeline can
  be size-capped externally as in §4).
