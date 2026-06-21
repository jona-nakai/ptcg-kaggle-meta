from __future__ import annotations

import json
import os
from pathlib import Path

import modal


APP_ROOT = "/root/ptcg-kaggle-meta"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("kagglehub")
    .add_local_dir("backend", remote_path=f"{APP_ROOT}/backend")
)

app = modal.App("ptcg-kaggle-meta-ingest")


def configure_kaggle_auth() -> None:
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if not username or not key:
        return

    kaggle_dir = Path("/root/.kaggle")
    kaggle_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    token_path = kaggle_dir / "kaggle.json"
    token_path.write_text(json.dumps({"username": username, "key": key}))
    token_path.chmod(0o600)
    os.environ.setdefault("KAGGLE_CONFIG_DIR", str(kaggle_dir))


@app.function(
    image=image,
    schedule=modal.Cron("15 * * * *"),
    secrets=[modal.Secret.from_name("ptcg-kaggle-meta")],
    ephemeral_disk=524_288,
    timeout=60 * 60 * 3,
)
def hourly_ingest(dataset_date: str | None = None) -> dict:
    import sys

    configure_kaggle_auth()
    sys.path.insert(0, APP_ROOT)

    from backend.ingest import ingest

    return ingest(Path("/tmp/ptcg-kaggle-meta/Data/kaggle"), dataset_date)


@app.local_entrypoint()
def main(date: str | None = None):
    print(hourly_ingest.remote(date))
