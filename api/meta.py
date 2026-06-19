from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.store import fetch_summary


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        summary = fetch_summary()
        if summary is not None:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("cache-control", "s-maxage=300, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(json.dumps(summary).encode())
            return

        self.send_response(404)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "No Supabase summary found"}).encode())
