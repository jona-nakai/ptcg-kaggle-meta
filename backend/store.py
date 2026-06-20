from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode
from typing import Any

from backend.archetypes import ARCHETYPE_ALGORITHM_VERSION


SUMMARY_KEY = "latest"
BATCH_SIZE = 500
CARD_IMAGE_BUCKET = "card-images"


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


def _binary_request(
    path: str,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str = "application/octet-stream",
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    url = os.environ["SUPABASE_URL"].rstrip("/") + path
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": content_type,
    }
    if extra_headers:
        headers.update(extra_headers)

    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Supabase binary request failed: HTTP {exc.code} {exc.reason}: {details}"
        ) from exc


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


def create_public_storage_bucket(bucket: str = CARD_IMAGE_BUCKET) -> None:
    if not is_supabase_configured():
        return

    try:
        _request(
            "/storage/v1/bucket",
            method="POST",
            body={"id": bucket, "name": bucket, "public": True},
        )
    except RuntimeError as exc:
        if "HTTP 409" not in str(exc):
            raise


def upload_storage_object(
    bucket: str,
    object_path: str,
    data: bytes,
    content_type: str,
    upsert: bool = True,
) -> str:
    _binary_request(
        f"/storage/v1/object/{quote(bucket)}/{quote(object_path, safe='/')}",
        method="POST",
        body=data,
        content_type=content_type,
        extra_headers={"x-upsert": "true" if upsert else "false"},
    )
    return (
        os.environ["SUPABASE_URL"].rstrip("/")
        + f"/storage/v1/object/public/{quote(bucket)}/{quote(object_path, safe='/')}"
    )


def delete_rows(table: str, filters: dict[str, str]) -> None:
    if not filters or not is_supabase_configured():
        return

    query = urlencode({key: f"eq.{value}" for key, value in filters.items()})
    _request(f"/rest/v1/{table}?{query}", method="DELETE")


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


def fetch_dataset_dates() -> list[str]:
    if not is_supabase_configured():
        return []

    rows = _request(
        "/rest/v1/daily_datasets?select=dataset_date&order=dataset_date.desc"
    )
    return [row["dataset_date"] for row in rows if row.get("dataset_date")]


def fetch_archetype_run_dates() -> list[str]:
    if not is_supabase_configured():
        return []

    rows = _request(
        "/rest/v1/archetype_runs"
        f"?algorithm_version=eq.{quote(ARCHETYPE_ALGORITHM_VERSION)}"
        "&select=dataset_date&order=dataset_date.desc"
    )
    return [row["dataset_date"] for row in rows if row.get("dataset_date")]


def fetch_daily_dataset(date: str) -> dict | None:
    rows = _request(
        f"/rest/v1/daily_datasets?dataset_date=eq.{quote(date)}&select=*&limit=1"
    )
    return rows[0] if rows else None


def fetch_top_cards_for_date(
    date: str,
    page: int,
    page_size: int = 10,
    include_extra: bool = False,
) -> list[dict]:
    offset = max(page - 1, 0) * page_size
    limit = page_size + 1 if include_extra else page_size
    query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "select": "card_id,copies_played,decks_played,cards(name,image_url)",
            "order": "copies_played.desc",
            "limit": str(limit),
            "offset": str(offset),
        },
        safe="(),.*",
    )
    rows = _request(f"/rest/v1/daily_card_usage?{query}")
    cards = []
    for row in rows:
        card = row.get("cards") or {}
        cards.append(
            {
                "id": row.get("card_id"),
                "name": card.get("name") or f"Card {row.get('card_id')}",
                "imageUrl": card.get("image_url"),
                "count": row.get("copies_played") or 0,
                "decksPlayed": row.get("decks_played") or 0,
            }
        )
    return cards


def fetch_all_card_usage_for_date(date: str) -> list[dict]:
    query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "select": "card_id,copies_played,decks_played,cards(name,image_url)",
            "order": "copies_played.desc",
        },
        safe="(),.*",
    )
    rows = _request(f"/rest/v1/daily_card_usage?{query}")
    cards = []
    for row in rows:
        card = row.get("cards") or {}
        cards.append(
            {
                "id": row.get("card_id"),
                "name": card.get("name") or f"Card {row.get('card_id')}",
                "imageUrl": card.get("image_url"),
                "copiesPlayed": row.get("copies_played") or 0,
                "decksPlayed": row.get("decks_played") or 0,
            }
        )
    return cards


def fetch_top_card_count_for_date(date: str) -> int:
    rows = _request(
        "/rest/v1/daily_card_usage?"
        + urlencode(
            {
                "dataset_date": f"eq.{date}",
                "select": "copies_played",
                "order": "copies_played.desc",
                "limit": "1",
            },
            safe="(),.*",
        )
    )
    if not rows:
        return 0
    return rows[0].get("copies_played") or 0


def _archetype_row(row: dict) -> dict:
    return {
        "id": row.get("archetype_id"),
        "slug": row.get("slug"),
        "name": row.get("name"),
        "deckCount": row.get("deck_count") or 0,
        "appearances": row.get("appearances") or 0,
        "wins": row.get("wins") or 0,
        "losses": row.get("losses") or 0,
        "winRate": float(row.get("win_rate") or 0),
        "metaShare": float(row.get("meta_share") or 0),
        "signatureCards": row.get("signature_cards") or [],
    }


def fetch_archetypes_for_date(date: str) -> list[dict]:
    query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "algorithm_version": f"eq.{ARCHETYPE_ALGORITHM_VERSION}",
            "select": "*",
            "order": "appearances.desc",
        },
        safe="(),.*",
    )
    rows = _request(f"/rest/v1/daily_archetypes?{query}")
    return [_archetype_row(row) for row in rows]


def fetch_archetype_detail(date: str, slug: str) -> dict | None:
    archetype_query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "algorithm_version": f"eq.{ARCHETYPE_ALGORITHM_VERSION}",
            "slug": f"eq.{slug}",
            "select": "*",
            "limit": "1",
        },
        safe="(),.*",
    )
    rows = _request(f"/rest/v1/daily_archetypes?{archetype_query}")
    if not rows:
        return None

    archetype = _archetype_row(rows[0])
    archetypes = fetch_archetypes_for_date(date)
    archetypes_by_id = {row["id"]: row for row in archetypes}

    card_query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "algorithm_version": f"eq.{ARCHETYPE_ALGORITHM_VERSION}",
            "archetype_id": f"eq.{archetype['id']}",
            "select": "card_id,inclusion_count,inclusion_pct,avg_copies,copies_total,cards(name,image_url)",
            "order": "inclusion_pct.desc",
        },
        safe="(),.*",
    )
    card_rows = _request(f"/rest/v1/archetype_cards?{card_query}")
    cards = []
    for row in card_rows:
        card = row.get("cards") or {}
        cards.append(
            {
                "id": row.get("card_id"),
                "name": card.get("name") or f"Card {row.get('card_id')}",
                "imageUrl": card.get("image_url"),
                "inclusionCount": row.get("inclusion_count") or 0,
                "inclusionPct": float(row.get("inclusion_pct") or 0),
                "avgCopies": float(row.get("avg_copies") or 0),
                "copiesTotal": row.get("copies_total") or 0,
            }
        )

    matchup_query = urlencode(
        {
            "dataset_date": f"eq.{date}",
            "algorithm_version": f"eq.{ARCHETYPE_ALGORITHM_VERSION}",
            "archetype_id": f"eq.{archetype['id']}",
            "select": "*",
            "order": "games.desc",
            "limit": "20",
        },
        safe="(),.*",
    )
    matchup_rows = _request(f"/rest/v1/archetype_matchups?{matchup_query}")
    matchups = []
    for row in matchup_rows:
        opponent = archetypes_by_id.get(row.get("opponent_archetype_id"))
        matchups.append(
            {
                "opponentId": row.get("opponent_archetype_id"),
                "opponentName": opponent["name"] if opponent else "Unknown",
                "opponentSlug": opponent["slug"] if opponent else "",
                "games": row.get("games") or 0,
                "wins": row.get("wins") or 0,
                "losses": row.get("losses") or 0,
                "winRate": float(row.get("win_rate") or 0),
            }
        )

    return {
        "date": date,
        "algorithmVersion": ARCHETYPE_ALGORITHM_VERSION,
        "archetype": archetype,
        "cards": cards,
        "matchups": matchups,
    }


def upsert_summary(summary: dict) -> None:
    if not is_supabase_configured():
        return

    _request(
        "/rest/v1/meta_summaries?on_conflict=key",
        method="POST",
        body=[{"key": SUMMARY_KEY, "payload": summary}],
        extra_headers={"prefer": "resolution=merge-duplicates"},
    )
