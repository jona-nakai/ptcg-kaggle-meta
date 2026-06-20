from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


ARCHETYPE_ALGORITHM_VERSION = "core-signature-v1"
MIN_SIGNATURE_CARDS = 1
MAX_SIGNATURE_CARDS = 2


@dataclass
class DeckStats:
    appearances: int = 0
    wins: int = 0
    losses: int = 0


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "archetype"


def is_basic_energy(name: str) -> bool:
    return name.lower().startswith("basic {") and name.lower().endswith(" energy")


def is_likely_core_card(name: str) -> bool:
    lower = name.lower()
    return " ex" in lower or " v" in lower or "gx" in lower or "'s " in lower


def card_signal_weight(name: str, global_deck_rate: float) -> float:
    if is_basic_energy(name):
        return 0.2

    weight = 1.0
    if is_likely_core_card(name):
        weight *= 1.7

    # Very common non-core-looking cards are usually broad support cards. Keep
    # some signal so dominant meta decks do not disappear when they are popular.
    if global_deck_rate >= 0.35 and not is_likely_core_card(name):
        weight *= 0.35
    elif global_deck_rate >= 0.2 and not is_likely_core_card(name):
        weight *= 0.65

    return weight


def archetype_id_for(dataset_date: str, key: tuple[int, ...]) -> str:
    encoded = f"{dataset_date}:{ARCHETYPE_ALGORITHM_VERSION}:{','.join(map(str, key))}"
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def deck_signature(
    card_counts: dict[int, int],
    card_names: dict[int, str],
    global_card_deck_counts: Counter[int],
    unique_deck_total: int,
) -> tuple[int, ...]:
    scored: list[tuple[float, int]] = []
    for card_id, count in card_counts.items():
        name = card_names.get(card_id, f"Card {card_id}")
        global_rate = global_card_deck_counts[card_id] / max(unique_deck_total, 1)
        score = count * card_signal_weight(name, global_rate)
        scored.append((score, card_id))

    scored.sort(reverse=True)
    signature = [
        card_id
        for _, card_id in scored
        if not is_basic_energy(card_names.get(card_id, ""))
    ][:MAX_SIGNATURE_CARDS]

    if len(signature) < MIN_SIGNATURE_CARDS:
        signature = [card_id for _, card_id in scored[:MAX_SIGNATURE_CARDS]]

    return tuple(signature)


def summarize_cards_for_group(
    deck_hashes: list[str],
    deck_cards: dict[str, dict[int, int]],
    deck_stats: dict[str, DeckStats],
    card_names: dict[int, str],
    global_weighted_inclusions: Counter[int],
    total_appearances: int,
) -> list[dict[str, Any]]:
    inclusion_counts: Counter[int] = Counter()
    copy_counts: Counter[int] = Counter()
    group_appearances = sum(deck_stats[deck_hash].appearances for deck_hash in deck_hashes)

    for deck_hash in deck_hashes:
        appearances = deck_stats[deck_hash].appearances
        for card_id, count in deck_cards[deck_hash].items():
            inclusion_counts[card_id] += appearances
            copy_counts[card_id] += appearances * count

    rows: list[dict[str, Any]] = []
    for card_id, inclusion_count in inclusion_counts.items():
        inclusion_pct = inclusion_count / max(group_appearances, 1)
        rows.append(
            {
                "card_id": card_id,
                "name": card_names.get(card_id, f"Card {card_id}"),
                "inclusion_count": inclusion_count,
                "inclusion_pct": inclusion_pct,
                "avg_copies": copy_counts[card_id] / max(group_appearances, 1),
                "copies_total": copy_counts[card_id],
                "global_inclusion_pct": global_weighted_inclusions[card_id]
                / max(total_appearances, 1),
            }
        )

    return sorted(
        rows,
        key=lambda row: (row["inclusion_pct"], row["avg_copies"], row["copies_total"]),
        reverse=True,
    )


def name_for_archetype(card_rows: list[dict[str, Any]]) -> str:
    candidates = [
        row
        for row in card_rows
        if row["inclusion_pct"] >= 0.25 and not is_basic_energy(row["name"])
    ]
    candidates.sort(
        key=lambda row: (
            row["inclusion_pct"] - row["global_inclusion_pct"],
            is_likely_core_card(row["name"]),
            row["inclusion_pct"],
        ),
        reverse=True,
    )
    names = [row["name"] for row in candidates[:MAX_SIGNATURE_CARDS]]
    return " / ".join(names) if names else "Other"


def build_archetype_dataset(compact: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    dataset_date = compact["daily_datasets"][0]["dataset_date"]
    deck_card_rows = compact["deck_cards"]
    battle_players = compact["battle_players"]

    card_names = {row["card_id"]: row["name"] for row in compact["cards"]}
    deck_cards: dict[str, dict[int, int]] = defaultdict(dict)
    for row in deck_card_rows:
        deck_cards[row["deck_hash"]][row["card_id"]] = row["count"]

    deck_stats: dict[str, DeckStats] = defaultdict(DeckStats)
    players_by_episode: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in battle_players:
        deck_hash = row["deck_hash"]
        deck_stats[deck_hash].appearances += 1
        if row.get("won"):
            deck_stats[deck_hash].wins += 1
        else:
            deck_stats[deck_hash].losses += 1
        players_by_episode[row["episode_id"]].append(row)

    global_card_deck_counts: Counter[int] = Counter()
    global_weighted_inclusions: Counter[int] = Counter()
    for deck_hash, cards in deck_cards.items():
        appearances = deck_stats[deck_hash].appearances
        for card_id in cards:
            global_card_deck_counts[card_id] += 1
            global_weighted_inclusions[card_id] += appearances

    unique_deck_total = len(deck_cards)
    total_appearances = sum(stats.appearances for stats in deck_stats.values())

    groups: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for deck_hash, cards in deck_cards.items():
        key = deck_signature(cards, card_names, global_card_deck_counts, unique_deck_total)
        groups[key].append(deck_hash)

    archetypes: list[dict[str, Any]] = []
    archetype_cards: list[dict[str, Any]] = []
    deck_archetypes: list[dict[str, Any]] = []
    deck_to_archetype: dict[str, str] = {}

    for key, deck_hashes in groups.items():
        card_rows = summarize_cards_for_group(
            deck_hashes,
            deck_cards,
            deck_stats,
            card_names,
            global_weighted_inclusions,
            total_appearances,
        )
        name = name_for_archetype(card_rows)
        archetype_id = archetype_id_for(dataset_date, key)
        slug = f"{slugify(name)}-{archetype_id[:6]}"
        appearances = sum(deck_stats[deck_hash].appearances for deck_hash in deck_hashes)
        wins = sum(deck_stats[deck_hash].wins for deck_hash in deck_hashes)
        losses = sum(deck_stats[deck_hash].losses for deck_hash in deck_hashes)

        signature_cards = [
            {
                "id": row["card_id"],
                "name": row["name"],
                "inclusionPct": row["inclusion_pct"],
            }
            for row in card_rows[:5]
        ]
        archetypes.append(
            {
                "dataset_date": dataset_date,
                "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
                "archetype_id": archetype_id,
                "slug": slug,
                "name": name,
                "deck_count": len(deck_hashes),
                "appearances": appearances,
                "wins": wins,
                "losses": losses,
                "win_rate": wins / max(wins + losses, 1),
                "meta_share": appearances / max(total_appearances, 1),
                "signature_cards": signature_cards,
            }
        )

        for deck_hash in deck_hashes:
            stats = deck_stats[deck_hash]
            deck_to_archetype[deck_hash] = archetype_id
            deck_archetypes.append(
                {
                    "dataset_date": dataset_date,
                    "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
                    "deck_hash": deck_hash,
                    "archetype_id": archetype_id,
                    "appearances": stats.appearances,
                    "wins": stats.wins,
                    "losses": stats.losses,
                }
            )

        for row in card_rows:
            archetype_cards.append(
                {
                    "dataset_date": dataset_date,
                    "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
                    "archetype_id": archetype_id,
                    "card_id": row["card_id"],
                    "inclusion_count": row["inclusion_count"],
                    "inclusion_pct": row["inclusion_pct"],
                    "avg_copies": row["avg_copies"],
                    "copies_total": row["copies_total"],
                }
            )

    matchup_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for players in players_by_episode.values():
        if len(players) != 2:
            continue
        player_a, player_b = sorted(players, key=lambda row: row["player_index"])
        archetype_a = deck_to_archetype.get(player_a["deck_hash"])
        archetype_b = deck_to_archetype.get(player_b["deck_hash"])
        if not archetype_a or not archetype_b:
            continue

        for player, archetype_id, opponent_id in (
            (player_a, archetype_a, archetype_b),
            (player_b, archetype_b, archetype_a),
        ):
            key = (archetype_id, opponent_id)
            matchup_counts[key]["games"] += 1
            if player.get("won"):
                matchup_counts[key]["wins"] += 1
            else:
                matchup_counts[key]["losses"] += 1

    archetype_matchups = [
        {
            "dataset_date": dataset_date,
            "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
            "archetype_id": archetype_id,
            "opponent_archetype_id": opponent_id,
            "games": counts["games"],
            "wins": counts["wins"],
            "losses": counts["losses"],
            "win_rate": counts["wins"] / max(counts["games"], 1),
        }
        for (archetype_id, opponent_id), counts in matchup_counts.items()
    ]

    archetype_run = {
        "dataset_date": dataset_date,
        "algorithm_version": ARCHETYPE_ALGORITHM_VERSION,
        "params": {
            "description": "Core-card signature grouping with generic support-card downweighting.",
            "maxSignatureCards": MAX_SIGNATURE_CARDS,
        },
        "archetype_count": len(archetypes),
        "processed_at": datetime.now(UTC).isoformat(),
    }

    return {
        "archetype_runs": [archetype_run],
        "daily_archetypes": archetypes,
        "deck_archetypes": deck_archetypes,
        "archetype_cards": archetype_cards,
        "archetype_matchups": archetype_matchups,
    }
