from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from backend.archetypes import ARCHETYPE_ALGORITHM_VERSION
from backend.store import _request, is_supabase_configured


REPO_ROOT = Path(__file__).resolve().parents[1]


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

    if not is_supabase_configured():
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    datasets = _request(
        "/rest/v1/daily_datasets?select=dataset_date&order=dataset_date.desc"
    )
    runs = _request(
        "/rest/v1/archetype_runs"
        f"?algorithm_version=eq.{quote(ARCHETYPE_ALGORITHM_VERSION)}"
        "&select=dataset_date"
    )

    dataset_dates = [row["dataset_date"] for row in datasets if row.get("dataset_date")]
    run_dates = {row["dataset_date"] for row in runs if row.get("dataset_date")}
    missing = [date for date in dataset_dates if date not in run_dates]

    print(f"Archetype algorithm: {ARCHETYPE_ALGORITHM_VERSION}")
    print(f"Daily datasets: {len(dataset_dates)}")
    print(f"Archetype runs: {len(run_dates)}")

    if not missing:
        print("All daily datasets have archetype runs.")
        return

    print("Missing archetype runs:")
    for date in missing:
        print(f"  {date}")

    print("\nBackfill with:")
    for date in missing:
        print(f"  modal run --env=dev modal_app.py --date {date}")

    raise SystemExit(1)


if __name__ == "__main__":
    main()
