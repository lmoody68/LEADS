"""
Shared cache layer for L.E.A.D.S. — Upstash Redis (REST) with an in-memory
fallback.

When UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN are set, JSON values are
stored in Upstash (durable + shared across processes/instances — important once
the app runs multi-worker or serverless, where local disk isn't shared). When
they're unset OR Upstash is unreachable, we transparently fall back to a
process-local in-memory dict. Every operation is GRACEFUL: any error degrades to
a cache-miss / no-op and never raises.

All keys are namespaced with "leads:" so this can safely share an Upstash
database with other apps (the DB is shared with MAESTRO).
"""
from __future__ import annotations

import json
import os
from typing import Any, List, Optional

import httpx

_PREFIX = "leads:"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_DEFAULT_TTL = 604800  # 7 days

_MEM: dict[str, str] = {}  # process-local fallback store


def _creds() -> tuple[Optional[str], Optional[str]]:
    url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    tok = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    return (url, tok) if (url and tok) else (None, None)


def enabled() -> bool:
    """True when Upstash REST creds are configured."""
    return _creds()[0] is not None


def status() -> dict:
    return {"backend": "upstash" if enabled() else "in-memory", "configured": enabled()}


def _cmd(args: List[Any]) -> Optional[Any]:
    """Run a single Redis command via the Upstash REST API. None on any error."""
    url, tok = _creds()
    if not url:
        return None
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {tok}"}, json=args, timeout=_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get("result")
        print(f"[cache] upstash HTTP {resp.status_code}")
    except Exception as exc:  # network / timeout / bad JSON — degrade to miss
        print(f"[cache] upstash error: {exc}")
    return None


def get(key: str) -> Optional[Any]:
    """Return the cached JSON value for `key`, or None on miss/error."""
    k = _PREFIX + key
    if enabled():
        raw = _cmd(["GET", k])
    else:
        raw = _MEM.get(k)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def set(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    """Cache a JSON-serializable `value` under `key` with a TTL (best-effort)."""
    k = _PREFIX + key
    try:
        payload = json.dumps(value)
    except Exception:
        return  # not serializable — skip silently
    if enabled():
        _cmd(["SET", k, payload, "EX", str(int(ttl))])
    else:
        _MEM[k] = payload
