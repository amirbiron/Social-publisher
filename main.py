"""
main.py — סקריפט ראשי שרץ כ-Render Cron Job

זרימה:
1. קורא את Google Sheet → שורות READY שהגיע זמנן
2. לכל שורה: נועל → מוריד מ-Drive → מעלה ל-Cloudinary → מפרסם → מעדכן סטטוס
"""

import logging
import sys
from datetime import datetime, timezone

from dateutil import parser as dtparser

from config import (
    TZ_IL,
    COL_STATUS,
    COL_NETWORK,
    COL_PUBLISH_AT,
    COL_CAPTION_IG,
    COL_CAPTION_FB,
    COL_DRIVE_FILE_ID,
    COL_CLOUDINARY_URL,
    COL_RESULT,
    COL_ERROR,
    STATUS_READY,
    STATUS_IN_PROGRESS,
    STATUS_POSTED,
    STATUS_ERROR,
    NETWORK_IG,
    NETWORK_FB,
    VIDEO_MIMES,
)
from google_api import (
    sheets_read_all_rows,
    sheets_update_cells,
    drive_download_with_metadata,
)
from cloud_storage import upload_to_cloudinary
from meta_publish import ig_publish_feed, fb_publish_feed

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("social-publisher")


# ═══════════════════════════════════════════════════════════════
#  Time Helpers
# ═══════════════════════════════════════════════════════════════

def is_due(publish_at_str: str, now_utc: datetime) -> bool:
    """
    בודק אם הגיע הזמן לפרסם.
    publish_at_str: תאריך+שעה בשעון ישראל (מהטבלה).
    now_utc: הזמן הנוכחי ב-UTC.
    """
    try:
        dt_il = dtparser.parse(publish_at_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid publish_at: {publish_at_str!r}")
        return False

    # אם אין timezone — מניחים ישראל
    if dt_il.tzinfo is None:
        dt_il = dt_il.replace(tzinfo=TZ_IL)

    dt_utc = dt_il.astimezone(timezone.utc)
    return dt_utc <= now_utc


# ═══════════════════════════════════════════════════════════════
#  Row Helpers
# ═══════════════════════════════════════════════════════════════

def get_cell(row: list[str], header: list[str], col_name: str, default: str = "") -> str:
    """שליפת ערך מהשורה לפי שם עמודה."""
    try:
        idx = header.index(col_name)
        return row[idx] if idx < len(row) else default
    except (ValueError, IndexError):
        return default


# ═══════════════════════════════════════════════════════════════
#  Process Single Row
# ═══════════════════════════════════════════════════════════════

def process_row(
    row: list[str],
    header: list[str],
    sheet_row_number: int,
) -> None:
    """
    מעבד שורה אחת: נועל → מוריד → מעלה → מפרסם → מעדכן.
    """
    network = get_cell(row, header, COL_NETWORK).strip().upper()
    drive_file_id = get_cell(row, header, COL_DRIVE_FILE_ID).strip()
    caption_ig = get_cell(row, header, COL_CAPTION_IG)
    caption_fb = get_cell(row, header, COL_CAPTION_FB)

    row_id = get_cell(row, header, "id", default=str(sheet_row_number))

    if not drive_file_id:
        _mark_error(header, sheet_row_number, "Missing drive_file_id")
        return

    if network not in (NETWORK_IG, NETWORK_FB):
        _mark_error(header, sheet_row_number, f"Unknown network: {network}")
        return

    # ── שלב 1: נעילה ──
    logger.info(f"Row {row_id}: Locking (IN_PROGRESS)")
    sheets_update_cells(sheet_row_number, {COL_STATUS: STATUS_IN_PROGRESS}, header)

    try:
        # ── שלב 2: הורדה מ-Drive + זיהוי סוג קובץ ──
        logger.info(f"Row {row_id}: Downloading from Drive ({drive_file_id})")
        file_bytes, metadata = drive_download_with_metadata(drive_file_id)
        mime_type = metadata.get("mimeType", "image/jpeg")
        file_name = metadata.get("name", "unknown")

        logger.info(
            f"Row {row_id}: File '{file_name}' | MIME: {mime_type} | "
            f"Size: {len(file_bytes)} bytes"
        )

        # ── שלב 3: העלאה ל-Cloudinary ──
        logger.info(f"Row {row_id}: Uploading to Cloudinary...")
        cloud_url = upload_to_cloudinary(file_bytes, mime_type, file_name)

        # ── שלב 4: פרסום ──
        if network == NETWORK_IG:
            caption = caption_ig or caption_fb  # fallback
            logger.info(f"Row {row_id}: Publishing to Instagram...")
            result_id = ig_publish_feed(cloud_url, caption, mime_type)
        else:
            caption = caption_fb or caption_ig  # fallback
            logger.info(f"Row {row_id}: Publishing to Facebook...")
            result_id = fb_publish_feed(cloud_url, caption, mime_type)

        # ── שלב 5: סימון הצלחה ──
        sheets_update_cells(
            sheet_row_number,
            {
                COL_STATUS: STATUS_POSTED,
                COL_CLOUDINARY_URL: cloud_url,
                COL_RESULT: str(result_id),
                COL_ERROR: "",
            },
            header,
        )
        logger.info(f"Row {row_id}: POSTED successfully ({result_id})")

    except Exception as e:
        logger.error(f"Row {row_id}: ERROR — {e}", exc_info=True)
        _mark_error(header, sheet_row_number, str(e))


def _mark_error(header: list[str], sheet_row_number: int, error_msg: str):
    """מסמן שורה כ-ERROR בטבלה."""
    # חותכים הודעות ארוכות מדי
    if len(error_msg) > 500:
        error_msg = error_msg[:497] + "..."

    sheets_update_cells(
        sheet_row_number,
        {COL_STATUS: STATUS_ERROR, COL_ERROR: error_msg},
        header,
    )


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    logger.info("═" * 50)
    logger.info("Social Publisher — Run started")
    logger.info("═" * 50)

    now_utc = datetime.now(timezone.utc)
    logger.info(f"Current UTC: {now_utc.isoformat()}")
    logger.info(
        f"Current Israel: "
        f"{now_utc.astimezone(TZ_IL).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # ── קריאת הטבלה ──
    header, rows = sheets_read_all_rows()

    if not header:
        logger.warning("Sheet is empty or header is missing.")
        return

    logger.info(f"Sheet has {len(rows)} data rows. Header: {header}")

    # ── סינון שורות שמוכנות לפרסום ──
    processed = 0
    skipped = 0

    for i, row in enumerate(rows, start=2):  # start=2 כי שורה 1 = header
        status = get_cell(row, header, COL_STATUS).strip().upper()

        if status != STATUS_READY:
            continue

        publish_at = get_cell(row, header, COL_PUBLISH_AT).strip()
        if not publish_at:
            logger.debug(f"Row {i}: No publish_at, skipping.")
            skipped += 1
            continue

        if not is_due(publish_at, now_utc):
            skipped += 1
            continue

        # ── מעבד את השורה ──
        process_row(row, header, i)
        processed += 1

    logger.info(f"Done. Processed: {processed}, Skipped (not due): {skipped}")


if __name__ == "__main__":
    main()
