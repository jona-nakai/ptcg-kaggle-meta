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


def select_dataset_row(rows: list[dict[str, str]], dataset_date: str | None = None) -> dict[str, str]:
    if not rows:
        raise FileNotFoundError("Downloaded index manifest did not include any rows.")

    if dataset_date:
        for row in rows:
            if row.get("date") == dataset_date:
                return row
        available = ", ".join(sorted(row.get("date", "") for row in rows if row.get("date")))
        raise ValueError(f"No Kaggle dataset found for {dataset_date}. Available dates: {available}")

    return sorted(rows, key=lambda row: row.get("date", ""))[-1]


def missing_dataset_rows(
    rows: list[dict[str, str]],
    existing_dates: set[str],
) -> list[dict[str, str]]:
    return [
        row
        for row in sorted(rows, key=lambda row: row.get("date", ""))
        if row.get("date") and row.get("date") not in existing_dates
    ]


def download_index_dataset(data_root: Path) -> Path:
    index_dir = data_root / "pokemon-tcg-ai-battle-episodes-index"
    index_dir.mkdir(parents=True, exist_ok=True)
    return Path(
        kagglehub.dataset_download(INDEX_DATASET, output_dir=str(index_dir))
    )


def download_daily_dataset(data_root: Path, selected: dict[str, str]) -> Path:
    slug = selected["daily_dataset_slug"]
    handle = normalize_dataset_handle(selected["daily_dataset_url"])
    dataset_dir = data_root / slug
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return Path(kagglehub.dataset_download(handle, output_dir=str(dataset_dir)))


def download_dataset(data_root: Path, dataset_date: str | None = None) -> tuple[Path, Path]:
    index_path = download_index_dataset(data_root)

    rows = read_index_rows(index_path / "manifest.csv")
    selected = select_dataset_row(rows, dataset_date)
    dataset_path = download_daily_dataset(data_root, selected)
    return index_path, dataset_path


def download_latest_dataset(data_root: Path) -> tuple[Path, Path]:
    return download_dataset(data_root)
