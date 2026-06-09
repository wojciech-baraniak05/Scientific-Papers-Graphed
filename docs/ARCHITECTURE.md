# Architektura


## Warstwy

```
Źródła danych  → ingestion → przetwarzanie → magazyn - MySQL → API backendu → frontend
```

| Warstwa | Odpowiedzialność | Kod |
|---|---|---|
| Ingestion | Typowane klienty HTTP | `app/ingestion/` |
| Przetwarzanie | Dekodowanie abstraktów, normalizacja id, uzgadnianie kodów krajów, wyprowadzanie zbioru krajów + `is_educational` | `app/processing/transform.py` |
| Magazyn | Schemat relacyjny, lista krawędzi cytowań | MySQL 8, `app/db/`, `sql/001_schema.sql` |
| API backendu | REST i Swagger, obsługa błędów | `app/api/`, `app/repository/`, `app/schemas/` |
| Frontend | interfejs Streamlit | `app/frontend/` |

Poza tym:
- Logging loguru
- Walidacja Pydantic,
- orkiestracja z `app/pipeline/`


## Kontekst

```mermaid
flowchart TB
    user([użytkownik])
    subgraph system[Paper Citation Explorer]
        app[Warstwowy system danych]
    end
    openalex[(API OpenAlex)]
    worldbank[(API World Bank)]
    hipolabs[(universities.hipolabs)]

    user -->|przegląda graf i analitykę| app
    app -->|prace, cytowania, autorstwa| openalex
    app -->|PKB, populacja, kraje| worldbank
    app -->|uczelnie wg kraju| hipolabs
```

---

## Kontener

```mermaid
flowchart TB
    user([Przeglądarka])

    subgraph compose[Sieć Docker Compose]
        frontend["Frontend\nStreamlit\n:8501"]
        backend["API backendu\nFastAPI + Uvicorn\n:8000"]
        mysql[("MySQL 8\n:3306\nwolumen nazwany")]
        pipeline["Pipeline zasilający\nCLI (jednorazowo)"]
    end

    openalex[(OpenAlex)]
    worldbank[(World Bank)]
    hipolabs[(hipolabs)]

    user -->|HTTP :8501| frontend
    frontend -->|REST JSON http://backend:8000| backend
    backend -->|SQLAlchemy ORM| mysql
    pipeline -->|klienty HTTP| openalex
    pipeline --> worldbank
    pipeline --> hipolabs
    pipeline -->|masowe upserty| mysql
```

Frontend komunikuje się tylko z backendem; tylko pipeline sięga do źródeł zewnętrznych. 

---

## Komponent (backend, frontend) 

```mermaid
flowchart LR
    subgraph fe[Frontend]
        app_py[streamlit_app.py]
        gtab[graph_tab.py]
        atab[analytics_tab.py]
        client[api_client.py]
        app_py --> gtab
        app_py --> atab
        gtab --> client
        atab --> client
    end

    subgraph be[Backend]
        routers["routers/\npapers · graph · fields · countries"]
        deps[deps.py get_db]
        cache[cache.py TTLCache]
        repo["repository/\npapers · countries · live"]
        schemas[schemas.py Pydantic]
        routers --> deps
        routers --> cache
        routers --> repo
        routers --> schemas
    end

    client -->|HTTP| routers
    repo --> db[(MySQL)]
```

---

## 5. Diagram wdrożenia UML

```mermaid
flowchart TB
    subgraph host[Host Docker]
        subgraph net[sieć bridge]
            fe["kontener - papers-frontend\nstreamlit:8501"]
            be["kontener - papers-backend\nuvicorn:8000"]
            db["kontener - papers-mysql\nmysql:3306"]
        end
        vol[("wolumen\npapers_mysql_data")]
    end
    browser["urządzenie - Przeglądarka"]
    ext["zewnętrzne źródła  OpenAlex / World Bank / hipolabs"]

    browser -->|:8501| fe
    fe -->|:8000| be
    be -->|:3306| db
    db --- vol
    be -.pipeline.-> ext
```

## 6. Przepływu żądań

**Zakładka 1 — graf cytowań.** `streamlit_app` → `graph_tab` → `api_client.search_papers`
→ `GET /api/papers/search` → repozytorium → MySQL; wybór pracy źródłowej →
`api_client.get_paper_graph` → `GET /api/papers/{id}/graph` → repozytorium buduje
węzły/krawędzie; kliknięcie węzła → `api_client.get_paper` →
`GET /api/papers/{id}` → prawy panel szczegółów.

**Zakładka 2 — analityka krajów.** `analytics_tab` → `api_client.get_fields` →
`GET /api/fields`; wybór dziedziny/domeny + metryki →
`api_client.field_country_ranking` / `domain_country_ranking` →
`GET /api/fields|domains/{id}/country-ranking` → repozytorium agreguje
`paper_countries ⋈ papers ⋈ countries`, wylicza wskaźniki i zwraca uszeregowaną
tabelę → `st.dataframe` + `st.bar_chart`.
