# Wybór technologii i uzasadnienie

| Warstwa | Wybór | Dlaczego |
|---|---|---|
| Język | Python 3.12 | Python bo prosty, 3.12 ma bardzo dobre wsparcie wszystkich bibliotek, nowsza wersja mogła by mieć problemy |
| Backend | FastAPI + Uvicorn | REST + JSON, walidacja Pydantic |
| ORM / driver | SQLAlchemy 2.0 + PyMySQL | Niezależne od bazy: MySQL w prod, SQLite w testach |
| Baza danych | MySQL 8 | Relacje mogą łatwo trozyć graf |
| Frontend | Streamlit | Wymagany frontend; agraph rysuje interaktywny graf węzłów i krawędzi oraz zwraca id klikniętego węzła, co steruje panelem szczegółów |
| Klient HTTP | httpx + tenacity, requests (frontend) | Timeouty, retry i backoff wobec niestabilnych publicznych API; frontend używa `requests` |
| Dane / wykresy | pandas + natywny Streamlit | szybka tabela + wizualizacja jednej metryki dla zakładki 2 |
| Logging | loguru | Konfigurowany raz jako sprawa przekrojowa; stderr (Docker/Loki) + rotujący plik; nigdy nie loguje sekretów |
| Testy | pytest + locust | Testy jednostkowe i API oraz podstawowe testy obciążenia/wydajności |
| Runtime | Docker + Compose | Wieloetapowe lekkie obrazy, użytkownik non-root, healthchecki, odnajdywanie usług po nazwie; nakładki dev / test / prod |

## Inne decyzje

- Zamknięta architektura warstwowa — frontend nigdy nie dotyka MySQL; mówi
  tylko do backendu przez HTTP. Do bazy sięga jedynie backend i jednorazowy pipeline.
- Cache danych statycznych — dataset ładowany jest raz, więc i backend
  (cache TTL w procesie), i frontend (`st.cache_data`) bezpiecznie cache'ują
  odpowiedzi czytane często.
