from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.store import (
    fetch_daily_dataset,
    fetch_dataset_dates,
    fetch_all_card_usage_for_date,
    fetch_archetypes_for_date,
    fetch_top_card_count_for_date,
    fetch_top_cards_for_date,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            requested_date = params.get("date", [None])[0]
            page = int(params.get("page", ["1"])[0])
            page = max(page, 1)

            dates = fetch_dataset_dates()
            if not dates:
                self.send_response(404)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No dataset dates found"}).encode())
                return

            latest_date = dates[0]
            selected_date = requested_date if requested_date in dates else latest_date
            dataset = fetch_daily_dataset(selected_date)
            page_size = 10
            card_rows = fetch_top_cards_for_date(
                selected_date,
                page,
                page_size=page_size,
                include_extra=True,
            )
            top_cards = card_rows[:page_size]
            max_card_count = fetch_top_card_count_for_date(selected_date)
            card_usage = fetch_all_card_usage_for_date(selected_date)
            archetypes = fetch_archetypes_for_date(selected_date)
            total_decks = int(dataset.get("episode_count") or 0) * 2 if dataset else 0

            body = {
                "date": selected_date,
                "latestDate": latest_date,
                "availableDates": dates,
                "redirected": requested_date is not None and requested_date not in dates,
                "page": page,
                "pageSize": page_size,
                "hasNextPage": len(card_rows) > page_size,
                "maxCardCount": max_card_count,
                "totalDecks": total_decks,
                "source": {
                    "date": selected_date,
                    "datasetSlug": dataset.get("dataset_slug") if dataset else None,
                    "datasetUrl": dataset.get("dataset_url") if dataset else None,
                },
                "cardUsage": card_usage,
                "archetypes": archetypes,
                "topCards": top_cards,
            }

            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("cache-control", "s-maxage=300, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        except Exception as exc:
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
