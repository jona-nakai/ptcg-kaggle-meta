from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import kagglehub

from backend.pipeline import read_index_rows


INDEX_DATASET = "kaggle/pokemon-tcg-ai-battle-episodes-index"
DAILY_DATASET_PREFIX = "pokemon-tcg-ai-battle-episodes"


def download_kaggle_dataset(handle: str, output_dir: Path) -> Path:
    try:
        return Path(kagglehub.dataset_download(handle, output_dir=str(output_dir)))
    except Exception as exc:
        message = str(exc)
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code == 404 or "404" in message:
            raise FileNotFoundError(f"Kaggle dataset does not exist: {handle}") from exc
        if status_code in (401, 403) or "403" in message:
            raise RuntimeError(
                "Kaggle denied access while downloading "
                f"{handle}. Check that the Modal secret has a current Kaggle API token "
                "and that the Kaggle account has accepted any required competition or dataset terms."
            ) from exc
        raise


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
    return download_kaggle_dataset(INDEX_DATASET, index_dir)


def download_daily_dataset(data_root: Path, selected: dict[str, str]) -> Path:
    slug = selected["daily_dataset_slug"]
    handle = normalize_dataset_handle(selected["daily_dataset_url"])
    dataset_dir = data_root / slug
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return download_kaggle_dataset(handle, dataset_dir)


def daily_dataset_row_for_date(dataset_date: str) -> dict[str, str]:
    slug = f"{DAILY_DATASET_PREFIX}-{dataset_date}"
    return {
        "date": dataset_date,
        "daily_dataset_slug": slug,
        "daily_dataset_url": f"https://www.kaggle.com/datasets/kaggle/{slug}",
        "episode_count": "0",
        "total_bytes": "0",
        "top_avg_score": "0",
        "median_avg_score": "0",
    }


def download_daily_dataset_if_exists(data_root: Path, dataset_date: str) -> tuple[dict[str, str], Path] | None:
    selected = daily_dataset_row_for_date(dataset_date)
    try:
        return selected, download_daily_dataset(data_root, selected)
    except FileNotFoundError:
        return None


def download_dataset(data_root: Path, dataset_date: str | None = None) -> tuple[Path, Path]:
    index_path = download_index_dataset(data_root)

    rows = read_index_rows(index_path / "manifest.csv")
    selected = select_dataset_row(rows, dataset_date)
    dataset_path = download_daily_dataset(data_root, selected)
    return index_path, dataset_path


def download_latest_dataset(data_root: Path) -> tuple[Path, Path]:
    return download_dataset(data_root)
