from __future__ import annotations

from collections.abc import Iterator, Sequence

import httpx

from app.ingestion._http import get_json

WORK_SELECT = (
    "id,doi,title,publication_year,cited_by_count,referenced_works,"
    "referenced_works_count,abstract_inverted_index,open_access,"
    "authorships,primary_topic"
)
STUB_SELECT = "id,doi,title,publication_year,cited_by_count,open_access,primary_topic"

_IDS_PER_BATCH = 50


class OpenAlexClient:
    def __init__(
        self,
        email: str = "",
        api_key: str = "",
        base_url: str = "https://api.openalex.org",
        timeout: float = 30.0,
        max_retries: int = 5,
        backoff_base: float = 1.0,
    ) -> None:
        self._email = email
        self._api_key = api_key
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        ua = f"paper-citation-explorer/0.1 (mailto:{email})" if email else "paper-citation-explorer/0.1"
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": ua, "Accept": "application/json"},
        )

    def _base_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self._email:
            params["mailto"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    def _get(self, path: str, params: dict) -> dict:
        merged = {**self._base_params(), **params}
        return get_json(
            self._client,
            path,
            params=merged,
            max_retries=self._max_retries,
            backoff_base=self._backoff_base,
            source="OpenAlex",
        )

    def iter_works(
        self,
        filter: str | None = None,
        sort: str = "cited_by_count:desc",
        select: str = WORK_SELECT,
        per_page: int = 200,
        max_records: int | None = None,
    ) -> Iterator[dict]:
        cursor: str | None = "*"
        yielded = 0
        while cursor:
            params: dict = {"per-page": per_page, "cursor": cursor, "select": select}
            if sort:
                params["sort"] = sort
            if filter:
                params["filter"] = filter
            data = self._get("/works", params)
            results = data.get("results", [])
            if not results:
                break
            for work in results:
                yield work
                yielded += 1
                if max_records is not None and yielded >= max_records:
                    return
            cursor = (data.get("meta") or {}).get("next_cursor")

    def fetch_works_by_ids(
        self, ids: Sequence[str], select: str = STUB_SELECT
    ) -> list[dict]:
        out: list[dict] = []
        ids = list(dict.fromkeys(ids))
        for start in range(0, len(ids), _IDS_PER_BATCH):
            batch = ids[start : start + _IDS_PER_BATCH]
            params = {
                "filter": "ids.openalex:" + "|".join(batch),
                "per-page": len(batch),
                "select": select,
            }
            data = self._get("/works", params)
            out.extend(data.get("results", []))
        return out

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAlexClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
