from __future__ import annotations

from pathlib import Path

import modal


APP_ROOT = "/root/ptcg-kaggle-meta"
REMOTE_DATA_ROOT = "/root/card-assets"
LOCAL_PDF = "/home/jonanakai/work/pokemon-ai/Data/Card_ID List_EN.pdf"
LOCAL_CSV = "/home/jonanakai/work/pokemon-ai/Data/EN_Card_Data.csv"
REMOTE_PDF = f"{REMOTE_DATA_ROOT}/Card_ID List_EN.pdf"
REMOTE_CSV = f"{REMOTE_DATA_ROOT}/EN_Card_Data.csv"


image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("PyMuPDF", "Pillow")
    .add_local_dir("backend", remote_path=f"{APP_ROOT}/backend")
    .add_local_file(LOCAL_PDF, remote_path=REMOTE_PDF)
    .add_local_file(LOCAL_CSV, remote_path=REMOTE_CSV)
)

app = modal.App("ptcg-kaggle-meta-card-assets")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("ptcg-kaggle-meta")],
    ephemeral_disk=524_288,
    timeout=60 * 60,
)
def import_card_images(action: str = "dry-run", limit: int = 0, force: bool = False) -> dict:
    import csv
    import io
    import sys
    from datetime import UTC, datetime

    import fitz
    from PIL import Image

    sys.path.insert(0, APP_ROOT)

    from backend.store import (
        CARD_IMAGE_BUCKET,
        create_public_storage_bucket,
        upload_storage_object,
        upsert_rows,
    )

    def load_cards(path: Path) -> list[dict]:
        cards_by_id: dict[int, dict] = {}
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                card_id = int(row["Card ID"])
                cards_by_id.setdefault(
                    card_id,
                    {
                        "card_id": card_id,
                        "name": row["Card Name"],
                    },
                )
        return [cards_by_id[card_id] for card_id in sorted(cards_by_id)]

    def extract_image_records(path: Path) -> list[dict]:
        doc = fitz.open(path)
        records: list[dict] = []
        seen_xrefs: set[int] = set()

        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                extracted = doc.extract_image(xref)
                width = int(extracted.get("width") or 0)
                height = int(extracted.get("height") or 0)
                if width < 120 or height < 160:
                    continue

                aspect = min(width, height) / max(width, height)
                if not 0.55 <= aspect <= 0.8:
                    continue

                rects = page.get_image_rects(xref)
                rect = rects[0] if rects else None
                records.append(
                    {
                        "page": page_index,
                        "x0": float(rect.x0) if rect else 0,
                        "y0": float(rect.y0) if rect else 0,
                        "xref": xref,
                        "width": width,
                        "height": height,
                        "bytes": extracted["image"],
                    }
                )

        records.sort(key=lambda row: (row["page"], row["y0"], row["x0"]))
        return records

    def to_webp_bytes(raw: bytes) -> bytes:
        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            image.thumbnail((300, 420), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=84, method=6)
            return output.getvalue()

    action = action.strip().lower()
    if action not in {"dry-run", "upload"}:
        raise ValueError("action must be 'dry-run' or 'upload'")

    cards = load_cards(Path(REMOTE_CSV))
    records = extract_image_records(Path(REMOTE_PDF))
    selected_cards = cards[: limit or None]
    selected_records = records[: limit or None]

    result = {
        "action": action,
        "cardRows": len(cards),
        "imageRows": len(records),
        "selectedRows": len(selected_cards),
        "samples": [
            {
                "cardId": card["card_id"],
                "name": card["name"],
                "image": {
                    "page": record["page"] + 1,
                    "width": record["width"],
                    "height": record["height"],
                },
            }
            for card, record in zip(selected_cards[:5], selected_records[:5], strict=False)
        ],
    }

    if len(records) != len(cards) and not force:
        result["error"] = "PDF image count did not match unique CSV card count. Rerun with force=true only after inspecting samples."
        return result

    if action == "dry-run":
        return result

    create_public_storage_bucket()
    now = datetime.now(UTC).isoformat()
    card_updates: list[dict] = []
    for card, record in zip(selected_cards, selected_records, strict=False):
        object_path = f"cards/en/{card['card_id']}.webp"
        public_url = upload_storage_object(
            CARD_IMAGE_BUCKET,
            object_path,
            to_webp_bytes(record["bytes"]),
            "image/webp",
            upsert=True,
        )
        card_updates.append(
            {
                "card_id": card["card_id"],
                "name": card["name"],
                "image_path": object_path,
                "image_url": public_url,
                "image_updated_at": now,
            }
        )

    upsert_rows("cards", card_updates, "card_id")
    result["uploadedRows"] = len(card_updates)
    return result


@app.local_entrypoint()
def main(action: str = "dry-run", limit: int = 0, force: bool = False):
    print(import_card_images.remote(action, limit, force))
