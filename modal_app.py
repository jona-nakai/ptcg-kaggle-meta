from __future__ import annotations

from pathlib import Path

import modal


APP_ROOT = "/root/ptcg-kaggle-meta"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("kagglehub")
    .add_local_dir("backend", remote_path=f"{APP_ROOT}/backend")
)

app = modal.App("ptcg-kaggle-meta-ingest")


@app.function(
    image=image,
    schedule=modal.Cron("15 * * * *"),
    secrets=[modal.Secret.from_name("ptcg-kaggle-meta")],
    ephemeral_disk=524_288,
    timeout=60 * 60 * 3,
)
def hourly_ingest(dataset_date: str | None = None) -> dict:
    import sys

    sys.path.insert(0, APP_ROOT)

    from backend.ingest import ingest

    return ingest(Path("/tmp/ptcg-kaggle-meta/Data/kaggle"), dataset_date)


@app.local_entrypoint()
def main(date: str | None = None):
    print(hourly_ingest.remote(date))
