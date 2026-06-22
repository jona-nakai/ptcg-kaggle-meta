from __future__ import annotations

from pathlib import Path

from backend.archetypes import ARCHETYPE_ALGORITHM_VERSION, build_archetype_dataset
from backend.kaggle_refresh import (
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
