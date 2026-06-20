from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.store import fetch_archetype_detail, fetch_dataset_dates


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            slug = params.get("slug", [""])[0]
            requested_date = params.get("date", [None])[0]

            dates = fetch_dataset_dates()
            if not dates:
                self.send_response(404)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No dataset dates found"}).encode())
                return

            latest_date = dates[0]
            selected_date = requested_date if requested_date in dates else latest_date
            detail = fetch_archetype_detail(selected_date, slug)
            if detail is None:
                self.send_response(404)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Archetype not found"}).encode())
                return

            detail["latestDate"] = latest_date
            detail["availableDates"] = dates
            detail["redirected"] = requested_date is not None and requested_date not in dates

            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("cache-control", "s-maxage=300, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(json.dumps(detail).encode())
        except Exception as exc:
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode())
