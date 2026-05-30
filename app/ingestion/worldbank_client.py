from __future__ import annotations

import httpx

from app.ingestion._http import get_json

GDP_INDICATOR = "NY.GDP.MKTP.CD"
POPULATION_INDICATOR = "SP.POP.TOTL"


class WorldBankClient:
    def __init__(
        self,
        base_url: str = "https://api.worldbank.org/v2",
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

    def _fetch_pages(self, path: str, base_params: dict) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while True:
            params = {**base_params, "format": "json", "page": page}
            payload = get_json(
                self._client,
                path,
                params=params,
                max_retries=self._max_retries,
                backoff_base=self._backoff_base,
                source="worldbank",
            )
            if not isinstance(payload, list) or len(payload) < 2:
                break
            meta, data = payload[0], payload[1]
            if data:
                rows.extend(data)
            pages = (meta or {}).get("pages") or 1
            if page >= pages:
                break
            page += 1
        return rows

    def get_countries(self) -> list[dict]:
        rows = self._fetch_pages("/country", {"per_page": 400})
        countries: list[dict] = []
        for row in rows:
            region = (row.get("region") or {}).get("value", "")
            if region == "Aggregates":
                continue
            countries.append(
                {
                    "iso3": row.get("id"),
                    "iso2": row.get("iso2Code"),
                    "name": row.get("name"),
                    "region": region,
                }
            )
        return countries

    def get_indicator(self, indicator: str) -> dict[str, tuple[float, int | None]]:
        rows = self._fetch_pages(
            f"/country/all/indicator/{indicator}", {"per_page": 1000, "mrnev": 1}
        )
        out: dict[str, tuple[float, int | None]] = {}
        for row in rows:
            iso3 = row.get("countryiso3code")
            value = row.get("value")
            if not iso3 or value is None:
                continue
            year = row.get("date")
            try:
                year_int: int | None = int(year) if year is not None else None
            except (TypeError, ValueError):
                year_int = None
            out[iso3] = (float(value), year_int)
        return out

    def get_gdp(self) -> dict[str, tuple[float, int | None]]:
        return self.get_indicator(GDP_INDICATOR)

    def get_population(self) -> dict[str, tuple[float, int | None]]:
        return self.get_indicator(POPULATION_INDICATOR)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WorldBankClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
