import httpx

from app.ingestion._http import get_json


class UniversitiesClient:
    def __init__(
        self,
        base_url: str = "http://universities.hipolabs.com",
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff_base: float = 1.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": "paper-citation-explorer/0.1"},
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    def fetch_all(self) -> list[dict]:
        data = get_json(
            self._client,
            "/search",
            params=None,
            max_retries=self._max_retries,
            backoff_base=self._backoff_base,
            source="hipolabs",
        )
        return data if isinstance(data, list) else []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UniversitiesClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
