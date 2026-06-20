from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api.archetype import handler as ArchetypeHandler
from api.meta import handler as MetaHandler


REPO_ROOT = Path(__file__).resolve().parents[1]


class DevApiHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/archetype"):
            return ArchetypeHandler.do_GET(self)
        if self.path.startswith("/api/meta"):
            return MetaHandler.do_GET(self)

        self.send_response(404)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"Not found"}')


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_env_file(REPO_ROOT / ".env")
    load_env_file(REPO_ROOT / ".env.local")

    port = int(os.environ.get("API_PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), DevApiHandler)
    print(f"Local API ready at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
