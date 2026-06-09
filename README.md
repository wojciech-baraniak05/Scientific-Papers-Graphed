# Paper Citation Explorer

## Jak uruchomić
Plik z env i odpalenie dockera
```bash
cp .env.example .env
docker compose up -d
```
Populacja bazy danych
```bash
docker compose exec backend python scripts/run_pipeline.py --scope popular --target-gb 1
```
Linki do stworzonych stron:
- Frontend: http://localhost:8501
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/api/health



## Środowiska do konteneryzacji

```bash
#dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

#test
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests

#prod
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Testy
Lokalne
```powershell
pip install -r requirements-dev.txt
pytest
```

```powershell
.\.venv\Scripts\python.exe -m pytest -q 
locust -f tests/locustfile.py --host http://localhost:8000
```


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
