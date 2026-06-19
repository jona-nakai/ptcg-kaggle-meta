from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import kagglehub

from backend.pipeline import read_index_rows


INDEX_DATASET = "kaggle/pokemon-tcg-ai-battle-episodes-index"


def normalize_dataset_handle(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in urlparse(value).path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "datasets":
            return f"{parts[1]}/{parts[2]}"
    return value


def download_latest_dataset(data_root: Path) -> tuple[Path, Path]:
    index_dir = data_root / "pokemon-tcg-ai-battle-episodes-index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = Path(
        kagglehub.dataset_download(INDEX_DATASET, output_dir=str(index_dir))
    )

    rows = read_index_rows(index_path / "manifest.csv")
    if not rows:
        raise FileNotFoundError("Downloaded index manifest did not include any rows.")

    latest = sorted(rows, key=lambda row: row.get("date", ""))[-1]
    slug = latest["daily_dataset_slug"]
    handle = normalize_dataset_handle(latest["daily_dataset_url"])
    dataset_dir = data_root / slug
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(kagglehub.dataset_download(handle, output_dir=str(dataset_dir)))
    return index_path, dataset_path
