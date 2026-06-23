from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.archetypes import ARCHETYPE_ALGORITHM_VERSION, build_archetype_dataset
from backend.kaggle_refresh import (
    download_daily_dataset_if_exists,
    download_daily_dataset,
    download_dataset,
    download_index_dataset,
    missing_dataset_rows,
)
from backend.pipeline import build_compact_dataset
from backend.pipeline import read_index_rows
from backend.store import (
    delete_rows,
    fetch_archetype_run_dates,
    fetch_dataset_dates,
    is_supabase_configured,
    upsert_rows,
    upsert_summary,
)


def storage_battle_players(rows: list[dict]) -> list[dict]:
    return [
        {
            **row,
            "won": False if row.get("won") is None else row.get("won"),
        }
        for row in rows
    ]


def write_index_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    fieldnames = [
        "date",
        "daily_dataset_slug",
        "daily_dataset_url",
        "episode_count",
        "total_bytes",
        "top_avg_score",
        "median_avg_score",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def candidate_direct_dates(rows: list[dict[str, str]], completed_dates: set[str]) -> list[str]:
    indexed_dates = sorted(row.get("date", "") for row in rows if row.get("date"))
    if not indexed_dates:
        return []

    latest_indexed = datetime.strptime(indexed_dates[-1], "%Y-%m-%d").date()
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    candidates = []
    current = latest_indexed + timedelta(days=1)
    while current <= today:
        value = current.isoformat()
        if value not in completed_dates:
            candidates.append(value)
        current += timedelta(days=1)
    return candidates


def ingest_dataset(index_path: Path, dataset_path: Path) -> dict:
    compact = build_compact_dataset(
        dataset_dir=dataset_path,
        index_manifest=index_path / "manifest.csv",
    )

    inferred_cards = compact["cards"]
    upsert_rows("cards", inferred_cards, "card_id")

    upsert_rows("daily_datasets", compact["daily_datasets"], "dataset_date")
    upsert_rows("decks", compact["decks"], "deck_hash")
    upsert_rows("deck_cards", compact["deck_cards"], "deck_hash,card_id")
    upsert_rows("battles", compact["battles"], "episode_id")
    upsert_rows("battle_players", storage_battle_players(compact["battle_players"]), "episode_id,player_index")
    upsert_rows("daily_card_usage", compact["daily_card_usage"], "dataset_date,card_id")

    archetypes = build_archetype_dataset(compact)
    dataset_date = compact["daily_datasets"][0]["dataset_date"]
    if compact["battle_players"] and not archetypes["daily_archetypes"]:
        raise RuntimeError(
            f"Parsed {len(compact['battle_players'])} battle player rows for {dataset_date}, "
            "but archetype generation produced zero archetypes."
        )

    archetype_filters = {
        "dataset_date": dataset_date,
        "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
    }
    for table in (
        "archetype_matchups",
        "archetype_cards",
        "deck_archetypes",
        "daily_archetypes",
        "archetype_runs",
    ):
        delete_rows(table, archetype_filters)

    upsert_rows("archetype_runs", archetypes["archetype_runs"], "dataset_date,algorithm_version")
    upsert_rows(
        "daily_archetypes",
        archetypes["daily_archetypes"],
        "dataset_date,algorithm_version,archetype_id",
    )
    upsert_rows(
        "deck_archetypes",
        archetypes["deck_archetypes"],
        "dataset_date,algorithm_version,deck_hash",
    )
    upsert_rows(
        "archetype_cards",
        archetypes["archetype_cards"],
        "dataset_date,algorithm_version,archetype_id,card_id",
    )
    upsert_rows(
        "archetype_matchups",
        archetypes["archetype_matchups"],
        "dataset_date,algorithm_version,archetype_id,opponent_archetype_id",
    )
    upsert_summary(compact["summary"])

    return {
        "summary": compact["summary"],
        "archetypes": archetypes["archetype_runs"][0],
        "datasetPath": str(dataset_path),
    }


def ingest(data_root: Path, dataset_date: str | None = None) -> dict:
    if dataset_date:
        index_path, dataset_path = download_dataset(data_root, dataset_date)
        result = ingest_dataset(index_path, dataset_path)
        return {
            "mode": "manual-date",
            "processed": 1,
            "dates": [result["summary"]["source"]["date"]],
            "results": [result],
        }

    index_path = download_index_dataset(data_root)
    rows = read_index_rows(index_path / "manifest.csv")

    if is_supabase_configured():
        dataset_dates = set(fetch_dataset_dates())
        archetype_dates = set(fetch_archetype_run_dates())
        completed_dates = dataset_dates & archetype_dates
        selected_rows = missing_dataset_rows(rows, completed_dates)
    else:
        dataset_dates = set()
        archetype_dates = set()
        completed_dates = set()
        selected_rows = missing_dataset_rows(rows, completed_dates)[-1:]

    downloaded_paths: dict[str, Path] = {}
    direct_rows: list[dict[str, str]] = []
    for candidate_date in candidate_direct_dates(rows, completed_dates):
        direct_result = download_daily_dataset_if_exists(data_root, candidate_date)
        if direct_result is None:
            continue
        direct_row, dataset_path = direct_result
        direct_rows.append(direct_row)
        downloaded_paths[direct_row["daily_dataset_slug"]] = dataset_path

    if direct_rows:
        existing_dates = {row.get("date") for row in rows}
        rows = rows + [row for row in direct_rows if row.get("date") not in existing_dates]
        write_index_rows(index_path / "manifest.csv", rows)
        selected_rows = missing_dataset_rows(rows, completed_dates)

    if not selected_rows:
        return {
            "mode": "scheduled",
            "processed": 0,
            "dates": [],
            "indexRows": len(rows),
            "datasetDates": len(dataset_dates),
            "archetypeDates": len(archetype_dates),
            "completedDates": len(completed_dates),
            "message": "No new Kaggle daily datasets found.",
        }

    results = []
    for selected in selected_rows:
        dataset_path = downloaded_paths.get(selected["daily_dataset_slug"])
        if dataset_path is None:
            dataset_path = download_daily_dataset(data_root, selected)
        results.append(ingest_dataset(index_path, dataset_path))

    return {
        "mode": "scheduled",
        "processed": len(results),
        "dates": [result["summary"]["source"]["date"] for result in results],
        "indexRows": len(rows),
        "datasetDates": len(dataset_dates),
        "archetypeDates": len(archetype_dates),
        "completedDates": len(completed_dates),
        "results": results,
    }
