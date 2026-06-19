from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote
from typing import Any


SUMMARY_KEY = "latest"
BATCH_SIZE = 500


def is_supabase_configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def _request(
    path: str,
    method: str = "GET",
    body: Any | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url = os.environ["SUPABASE_URL"].rstrip("/") + path
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Supabase request failed: HTTP {exc.code} {exc.reason}: {details}"
        ) from exc
    return json.loads(payload.decode("utf-8")) if payload else None


def _table_path(table: str, on_conflict: str | None = None) -> str:
    path = f"/rest/v1/{table}"
    if on_conflict:
        path += f"?on_conflict={quote(on_conflict, safe=',')}"
    return path


def upsert_rows(table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows or not is_supabase_configured():
        return

    for start in range(0, len(rows), BATCH_SIZE):
        _request(
            _table_path(table, on_conflict),
            method="POST",
            body=rows[start : start + BATCH_SIZE],
            extra_headers={
                "prefer": "resolution=merge-duplicates",
            },
        )


def fetch_summary() -> dict | None:
    if not is_supabase_configured():
        return None

    try:
        rows = _request(
            f"/rest/v1/meta_summaries?key=eq.{SUMMARY_KEY}&select=payload&limit=1"
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None

    if not rows:
        return None
    payload = rows[0].get("payload")
    return payload if isinstance(payload, dict) else None


def upsert_summary(summary: dict) -> None:
    if not is_supabase_configured():
        return

    _request(
        "/rest/v1/meta_summaries?on_conflict=key",
        method="POST",
        body=[{"key": SUMMARY_KEY, "payload": summary}],
        extra_headers={"prefer": "resolution=merge-duplicates"},
    )
