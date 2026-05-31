import time

import pytest

_THRESHOLD_SECONDS = 0.5


def _timed(client, path: str, params: dict | None = None) -> float:
    start = time.perf_counter()
    resp = client.get(path, params=params or {})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    return elapsed


@pytest.mark.parametrize(
    "path, params",
    [
        ("/api/health", None),
        ("/api/fields", None),
        ("/api/papers/search", {"q": "learning", "limit": 20}),
        ("/api/papers/W1", None),
        ("/api/papers/W1/graph", {"direction": "cites", "limit": 50}),
        ("/api/papers/W2/graph", {"direction": "cited_by", "limit": 50}),
        ("/api/fields/22/country-ranking", {"order_by": "papers_per_gdp", "limit": 30}),
        ("/api/domains/3/country-ranking", {"order_by": "papers", "limit": 30}),
    ],
)
def test_endpoint_under_threshold(client, path, params):
    elapsed = _timed(client, path, params)
    assert elapsed < _THRESHOLD_SECONDS, f"{path} took {elapsed:.3f}s"
