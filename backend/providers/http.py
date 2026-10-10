"""Shared HTTP client with timeouts and retries for third-party APIs."""

from __future__ import annotations

import logging
import time

import httpx

from core.errors import UpstreamError

log = logging.getLogger(__name__)

USER_AGENT = "weather-aware-truck-routing/1.0 (assessment project)"
RETRY_STATUSES = {429, 500, 502, 503, 504}

_client = httpx.Client(
    timeout=httpx.Timeout(25.0, connect=8.0),
    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    follow_redirects=True,
)


def request(
    method: str,
    url: str,
    *,
    service: str,
    params=None,
    data=None,
    retries: int = 2,
    backoff_s: float = 0.7,
) -> httpx.Response:
    """Send a request, retrying network errors and busy/5xx answers.

    Returns the final response for any non-retryable status (including 4xx) so
    the caller can turn it into a specific message. Raises UpstreamError when
    the service stays unreachable or busy.
    """
    last_status = None
    for attempt in range(retries + 1):
        try:
            resp = _client.request(method, url, params=params, data=data)
        except httpx.TimeoutException:
            log.warning("%s timed out (attempt %d)", service, attempt + 1)
            last_status = "timeout"
        except httpx.HTTPError as exc:
            log.warning("%s network error: %s (attempt %d)", service, exc, attempt + 1)
            last_status = "network"
        else:
            if resp.status_code not in RETRY_STATUSES:
                return resp
            last_status = resp.status_code
            log.warning("%s returned %s (attempt %d)", service, resp.status_code, attempt + 1)
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit() and int(retry_after) <= 5:
                time.sleep(int(retry_after))
                continue
        if attempt < retries:
            time.sleep(backoff_s * (2**attempt))

    if last_status == 429:
        raise UpstreamError(
            f"{service.upper()}_RATE_LIMITED",
            f"The {service} service is receiving too many requests right now. Wait a minute and try again.",
        )
    if last_status == "timeout":
        raise UpstreamError(
            f"{service.upper()}_TIMEOUT",
            f"The {service} service took too long to answer. Try again in a moment.",
        )
    raise UpstreamError(
        f"{service.upper()}_UNAVAILABLE",
        f"The {service} service is unavailable right now. Try again in a minute.",
    )
