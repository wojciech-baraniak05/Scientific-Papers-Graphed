from __future__ import annotations

import httpx
from loguru import logger
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    pass


def get_json(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    max_retries: int = 5,
    backoff_base: float = 1.0,
    source: str = "http",
):
    def _do():
        response = client.get(url, params=params)
        if response.status_code in _RETRYABLE_STATUS:
            raise RetryableHTTPError(f"{response.status_code} from {url}")
        response.raise_for_status()
        return response.json()

    retryer = Retrying(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=backoff_base, min=1, max=60),
        retry=retry_if_exception_type(
            (RetryableHTTPError, httpx.TransportError, httpx.TimeoutException)
        ),
        before_sleep=lambda rs: logger.warning(
            "{} request failed ({}); retry {}", source, rs.outcome.exception(), rs.attempt_number
        ),
        reraise=True,
    )
    return retryer(_do)
