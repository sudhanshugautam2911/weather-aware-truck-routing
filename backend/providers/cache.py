"""Cache helpers that never break a request: if the cache (e.g. Redis) is down,
we just fetch fresh data."""

import logging

from django.core.cache import cache

log = logging.getLogger(__name__)


def get_many(keys: list[str]) -> dict:
    try:
        return cache.get_many(keys)
    except Exception as exc:  # noqa: BLE001 - any cache backend failure
        log.warning("cache read failed: %s", exc)
        return {}


def set_many(values: dict, timeout: int) -> None:
    try:
        cache.set_many(values, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache write failed: %s", exc)


def get(key: str):
    return get_many([key]).get(key)


def set(key: str, value, timeout: int) -> None:  # noqa: A001 - mirrors Django's API
    set_many({key: value}, timeout)
