from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "Data" / "kaggle"
INDEX_MANIFEST = DATA_ROOT / "pokemon-tcg-ai-battle-episodes-index" / "manifest.csv"


def read_index_rows(path: Path = INDEX_MANIFEST) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def latest_dataset_from_index(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    return sorted(rows, key=lambda row: row.get("date", ""))[-1]


def latest_dataset_dir(rows: list[dict[str, str]]) -> Path:
    latest = latest_dataset_from_index(rows)
    slug = latest.get("daily_dataset_slug")
    if not slug:
        raise FileNotFoundError("No daily_dataset_slug found in index manifest.")
    return DATA_ROOT / slug


def dataset_from_dir(rows: list[dict[str, str]], dataset_dir: Path) -> dict[str, str]:
    slug = dataset_dir.name
    for row in rows:
        if row.get("daily_dataset_slug") == slug:
            return row
    return latest_dataset_from_index(rows)


def read_first_visualize_object(path: Path, max_bytes: int = 4_000_000) -> dict:
    marker = '"visualize": ['
    decoder = json.JSONDecoder()
    buffer = ""
    object_start: int | None = None

    with path.open(encoding="utf-8") as f:
        while len(buffer) < max_bytes:
            chunk = f.read(64_000)
            if not chunk:
                break
            buffer += chunk

            if object_start is None:
                marker_at = buffer.find(marker)
                if marker_at == -1:
                    continue
                object_start = buffer.find("{", marker_at)
                if object_start == -1:
                    continue

            try:
                value, _ = decoder.raw_decode(buffer[object_start:])
                if isinstance(value, dict):
                    return value
                raise ValueError(f"First visualize item is not an object in {path.name}")
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not parse first visualize object from {path.name}")


def read_json_value_after_key(buffer: str, key: str):
    decoder = json.JSONDecoder()
    marker = f'"{key}":'
    marker_at = buffer.find(marker)
    if marker_at == -1:
        return None
    value_start = marker_at + len(marker)
    while value_start < len(buffer) and buffer[value_start].isspace():
        value_start += 1
    value, _ = decoder.raw_decode(buffer[value_start:])
    return value


def read_battle_header(path: Path, max_bytes: int = 512_000) -> dict:
    buffer = ""
    with path.open(encoding="utf-8") as f:
        while len(buffer) < max_bytes:
            chunk = f.read(64_000)
            if not chunk:
                break
            buffer += chunk
            if '"steps":' in buffer:
                break

    return {
        "id": read_json_value_after_key(buffer, "id"),
        "info": read_json_value_after_key(buffer, "info") or {},
        "rewards": read_json_value_after_key(buffer, "rewards") or [],
        "statuses": read_json_value_after_key(buffer, "statuses") or [],
    }


def deck_cards_from_visualize(visualize: dict) -> list[dict[str, int | str]]:
    cards: list[dict[str, int | str]] = []
    current = visualize.get("current")
    if not isinstance(current, dict):
        return cards

    players = current.get("players")
    if not isinstance(players, list):
        return cards

    for player in players:
        if not isinstance(player, dict):
            continue
        deck = player.get("deck")
        if not isinstance(deck, list):
            continue
        for card in deck:
            if not isinstance(card, dict):
                continue
            card_id = card.get("id")
            name = card.get("name")
            if isinstance(card_id, int) and isinstance(name, str):
                cards.append({"id": card_id, "name": name})
    return cards


def player_decks_from_visualize(visualize: dict) -> list[list[dict[str, int | str]]]:
    current = visualize.get("current")
    if not isinstance(current, dict):
        return []

    players = current.get("players")
    if not isinstance(players, list):
        return []

    decks: list[list[dict[str, int | str]]] = []
    for player in players:
        deck_cards: list[dict[str, int | str]] = []
        if not isinstance(player, dict):
            decks.append(deck_cards)
            continue
        deck = player.get("deck")
        if not isinstance(deck, list):
            decks.append(deck_cards)
            continue
        for card in deck:
            if not isinstance(card, dict):
                continue
            card_id = card.get("id")
            name = card.get("name")
            if isinstance(card_id, int) and isinstance(name, str):
                deck_cards.append({"id": card_id, "name": name})
        decks.append(deck_cards)
    return decks


def deck_hash(cards: list[dict[str, int | str]]) -> str:
    counts = Counter(int(card["id"]) for card in cards)
    encoded = ",".join(f"{card_id}:{count}" for card_id, count in sorted(counts.items()))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def winner_from_rewards(rewards: list | None) -> int | None:
    if not isinstance(rewards, list) or len(rewards) < 2:
        return None
    if rewards[0] == rewards[1]:
        return None
    if rewards[0] == 1:
        return 0
    if rewards[1] == 1:
        return 1
    return 0 if rewards[0] > rewards[1] else 1


def build_compact_dataset(
    dataset_dir: Path | None = None,
    index_manifest: Path = INDEX_MANIFEST,
) -> dict[str, list[dict] | dict]:
    rows = read_index_rows(index_manifest)
    dataset_dir = dataset_dir or latest_dataset_dir(rows)
    selected = dataset_from_dir(rows, dataset_dir)
    dataset_date = selected.get("date")
    if not dataset_date:
        raise ValueError("Index manifest did not include a date for the selected dataset.")

    battle_files = sorted(dataset_dir.glob("*.json"))
    cards_by_id: dict[int, str] = {}
    battles: list[dict] = []
    battle_players: list[dict] = []
    decks_by_hash: dict[str, dict] = {}
    deck_cards_by_key: dict[tuple[str, int], dict] = {}
    card_copy_counts: Counter[int] = Counter()
    card_deck_counts: Counter[int] = Counter()
    parse_errors: list[dict[str, str]] = []

    for path in battle_files:
        try:
            header = read_battle_header(path)
            visualize = read_first_visualize_object(path)
            player_decks = player_decks_from_visualize(visualize)
            if len(player_decks) < 2:
                raise ValueError("Expected two player decks")

            info = header.get("info") or {}
            team_names = info.get("TeamNames") or ["", ""]
            rewards = header.get("rewards") or []
            statuses = header.get("statuses") or []
            episode_id = int(info.get("EpisodeId") or path.stem)
            winner_index = winner_from_rewards(rewards)

            battles.append(
                {
                    "episode_id": episode_id,
                    "dataset_date": dataset_date,
                    "battle_uuid": header.get("id"),
                    "player0_name": team_names[0] if len(team_names) > 0 else "",
                    "player1_name": team_names[1] if len(team_names) > 1 else "",
                    "winner_index": winner_index,
                    "player0_reward": rewards[0] if len(rewards) > 0 else None,
                    "player1_reward": rewards[1] if len(rewards) > 1 else None,
                    "player0_status": statuses[0] if len(statuses) > 0 else None,
                    "player1_status": statuses[1] if len(statuses) > 1 else None,
                    "step_count": None,
                }
            )

            for player_index, deck in enumerate(player_decks[:2]):
                hash_value = deck_hash(deck)
                card_counts = Counter(int(card["id"]) for card in deck)
                for card in deck:
                    cards_by_id[int(card["id"])] = str(card["name"])
                for card_id, count in card_counts.items():
                    deck_cards_by_key[(hash_value, card_id)] = {
                        "deck_hash": hash_value,
                        "card_id": card_id,
                        "count": count,
                    }
                    card_copy_counts[card_id] += count
                    card_deck_counts[card_id] += 1

                decks_by_hash[hash_value] = {
                    "deck_hash": hash_value,
                    "card_count": len(deck),
                    "first_seen_date": dataset_date,
                    "last_seen_date": dataset_date,
                }
                battle_players.append(
                    {
                        "episode_id": episode_id,
                        "player_index": player_index,
                        "player_name": team_names[player_index]
                        if player_index < len(team_names)
                        else "",
                        "deck_hash": hash_value,
                        "reward": rewards[player_index]
                        if player_index < len(rewards)
                        else None,
                        "status": statuses[player_index]
                        if player_index < len(statuses)
                        else None,
                        "won": None if winner_index is None else winner_index == player_index,
                    }
                )
        except Exception as exc:
            parse_errors.append({"file": path.name, "error": str(exc)})

    cards = [
        {"card_id": card_id, "name": name, "raw": None}
        for card_id, name in sorted(cards_by_id.items())
    ]
    daily_card_usage = [
        {
            "dataset_date": dataset_date,
            "card_id": card_id,
            "copies_played": card_copy_counts[card_id],
            "decks_played": card_deck_counts[card_id],
        }
        for card_id in sorted(card_copy_counts)
    ]
    top_cards = [
        {
            "id": card_id,
            "name": cards_by_id.get(card_id, f"Card {card_id}"),
            "count": count,
        }
        for card_id, count in card_copy_counts.most_common(5)
    ]

    summary = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": {
            "date": selected.get("date"),
            "datasetSlug": selected.get("daily_dataset_slug"),
            "datasetUrl": selected.get("daily_dataset_url"),
            "indexRows": len(rows),
            "reportedEpisodeCount": int(selected.get("episode_count") or 0),
            "reportedTotalBytes": int(selected.get("total_bytes") or 0),
            "topAvgScore": float(selected.get("top_avg_score") or 0),
            "medianAvgScore": float(selected.get("median_avg_score") or 0),
        },
        "totals": {
            "battleFiles": len(battle_files),
            "parsedBattles": len(battles),
            "parsedDecks": len(battle_players),
            "cardCopies": sum(card_copy_counts.values()),
            "uniqueCards": len(cards_by_id),
            "uniqueDecks": len(decks_by_hash),
            "parseErrors": len(parse_errors),
        },
        "topCards": top_cards,
        "parseErrors": parse_errors[:10],
    }

    return {
        "daily_datasets": [
            {
                "dataset_date": selected.get("date"),
                "dataset_slug": selected.get("daily_dataset_slug"),
                "dataset_url": selected.get("daily_dataset_url"),
                "episode_count": int(selected.get("episode_count") or 0),
                "total_bytes": int(selected.get("total_bytes") or 0),
                "top_avg_score": float(selected.get("top_avg_score") or 0),
                "median_avg_score": float(selected.get("median_avg_score") or 0),
            }
        ],
        "cards": cards,
        "battles": battles,
        "decks": list(decks_by_hash.values()),
        "deck_cards": list(deck_cards_by_key.values()),
        "battle_players": battle_players,
        "daily_card_usage": daily_card_usage,
        "summary": summary,
    }
