from __future__ import annotations

from pathlib import Path

from backend.kaggle_refresh import download_latest_dataset
from backend.pipeline import build_compact_dataset
from backend.store import upsert_rows, upsert_summary


def ingest(data_root: Path) -> dict:
    index_path, dataset_path = download_latest_dataset(data_root)
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
    upsert_rows("battle_players", compact["battle_players"], "episode_id,player_index")
    upsert_rows("daily_card_usage", compact["daily_card_usage"], "dataset_date,card_id")
    upsert_summary(compact["summary"])

    return {
        "summary": compact["summary"],
        "datasetPath": str(dataset_path),
    }
