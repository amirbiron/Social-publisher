"""
main.py — סקריפט ראשי שרץ כ-Render Cron Job

זרימה:
1. קורא את Google Sheet → שורות READY שהגיע זמנן
2. לכל שורה: נועל → מוריד מ-Drive → מעלה ל-Cloudinary → מפרסם → מעדכן סטטוס
"""

import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from dateutil import parser as dtparser

from config import (
    TZ_IL,
    COL_STATUS,
    COL_NETWORK,
    COL_POST_TYPE,
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
    POST_TYPE_FEED,
    POST_TYPE_REELS,
    VIDEO_MIMES,
)
from google_api import (
    sheets_read_all_rows,
    sheets_update_cells,
    drive_download_with_metadata,
)
from cloud_storage import upload_to_cloudinary, delete_from_cloudinary
from media_processor import normalize_media, MediaProcessingError
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
    post_type = get_cell(row, header, COL_POST_TYPE).strip().upper() or POST_TYPE_FEED
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

        # ── שלב 2.5: נרמול מדיה ──
        logger.info(f"Row {row_id}: Normalizing media...")
        file_bytes, mime_type, file_name = normalize_media(
            file_bytes, mime_type, file_name, post_type
        )
        logger.info(
            f"Row {row_id}: Normalized → {file_name} | "
            f"MIME: {mime_type} | Size: {len(file_bytes)} bytes"
        )

        # ── שלב 3: העלאה ל-Cloudinary ──
        logger.info(f"Row {row_id}: Uploading to Cloudinary...")
        cloud_url = upload_to_cloudinary(file_bytes, mime_type, file_name)

        # ── שלב 4: פרסום ──
        if network == NETWORK_IG:
            caption = caption_ig or caption_fb  # fallback
            logger.info(f"Row {row_id}: Publishing to Instagram ({post_type})...")
            result_id = ig_publish_feed(cloud_url, caption, mime_type, post_type)
        else:
            caption = caption_fb or caption_ig  # fallback
            logger.info(f"Row {row_id}: Publishing to Facebook ({post_type})...")
            result_id = fb_publish_feed(cloud_url, caption, mime_type, post_type)

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
        error_detail = (
            f"[{e.error_code}] {e}" if isinstance(e, MediaProcessingError)
            else str(e)
        )
        # Extract Meta API error details from response body
        if hasattr(e, "response") and e.response is not None:
            try:
                error_detail += f" | Meta response: {e.response.text}"
            except Exception:
                pass
        logger.error(f"Row {row_id}: ERROR — {error_detail}", exc_info=True)
        _mark_error(header, sheet_row_number, error_detail)


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
#  Cloudinary Cleanup
# ═══════════════════════════════════════════════════════════════

CLOUDINARY_RETENTION_DAYS = int(os.environ.get("CLOUDINARY_RETENTION_DAYS", "10"))

# חילוץ public_id מ-URL של Cloudinary
# https://res.cloudinary.com/CLOUD/image/upload/v123/social-publisher/abc.jpg
#   → social-publisher/abc
_CLOUDINARY_URL_RE = re.compile(
    r"https?://res\.cloudinary\.com/[^/]+/(?P<rtype>image|video)/upload/(?:v\d+/)?(?P<pid>.+)\.\w+$"
)


def cleanup_old_cloudinary_assets(
    header: list[str],
    rows: list[list[str]],
    now_utc: datetime,
) -> int:
    """
    מוחק נכסים מ-Cloudinary עבור שורות POSTED
    שפורסמו לפני יותר מ-CLOUDINARY_RETENTION_DAYS ימים.
    מחזיר מספר הנכסים שנמחקו.
    """
    cutoff = now_utc - timedelta(days=CLOUDINARY_RETENTION_DAYS)
    deleted = 0

    for i, row in enumerate(rows, start=2):
        status = get_cell(row, header, COL_STATUS).strip().upper()
        if status != STATUS_POSTED:
            continue

        cloud_url = get_cell(row, header, COL_CLOUDINARY_URL).strip()
        if not cloud_url:
            continue

        publish_at = get_cell(row, header, COL_PUBLISH_AT).strip()
        if not publish_at:
            continue

        # בדיקה אם עברו מספיק ימים
        try:
            dt_il = dtparser.parse(publish_at)
        except (ValueError, TypeError):
            continue

        if dt_il.tzinfo is None:
            dt_il = dt_il.replace(tzinfo=TZ_IL)

        if dt_il.astimezone(timezone.utc) > cutoff:
            continue

        # חילוץ public_id ו-resource_type מה-URL
        match = _CLOUDINARY_URL_RE.match(cloud_url)
        if not match:
            logger.warning(f"Row {i}: Cannot parse Cloudinary URL: {cloud_url}")
            continue

        public_id = match.group("pid")
        resource_type = match.group("rtype")

        logger.info(f"Row {i}: Deleting old asset {public_id} ({resource_type})")
        if delete_from_cloudinary(public_id, resource_type=resource_type):
            sheets_update_cells(i, {COL_CLOUDINARY_URL: ""}, header)
            deleted += 1

    return deleted


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

    # ── ניקוי נכסים ישנים מ-Cloudinary ──
    deleted = cleanup_old_cloudinary_assets(header, rows, now_utc)
    if deleted:
        logger.info(f"Cloudinary cleanup: deleted {deleted} old asset(s)")


if __name__ == "__main__":
    main()
