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
Obciążeniowe
```powershell
.\.venv\Scripts\python.exe -m pytest -q 
locust -f tests/locustfile.py --host http://localhost:8000
```
