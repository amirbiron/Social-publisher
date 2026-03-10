"""
cloud_storage.py — העלאה ל-Cloudinary וקבלת URL ציבורי
"""

import logging
import tempfile

import cloudinary
import cloudinary.uploader

from config import (
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
    VIDEO_MIMES,
)

logger = logging.getLogger(__name__)

# ─── Init Cloudinary ─────────────────────────────────────────
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


def upload_to_cloudinary(
    file_bytes: bytes,
    mime_type: str,
    file_name: str = "media",
) -> str:
    """
    מעלה קובץ (תמונה/וידאו) ל-Cloudinary.
    מחזיר secure_url (HTTPS).

    - לוידאו: resource_type="video"
    - לתמונה: resource_type="image"
    """
    is_video = mime_type in VIDEO_MIMES
    resource_type = "video" if is_video else "image"

    # סיומת לקובץ זמני (Cloudinary צריך לזהות פורמט)
    suffix = _get_suffix(mime_type)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()

        logger.info(
            f"Uploading to Cloudinary: {file_name} "
            f"({len(file_bytes)} bytes, {resource_type})"
        )

        result = cloudinary.uploader.upload(
            tmp.name,
            resource_type=resource_type,
            # folder אופציונלי — אפשר להוסיף לארגון
            folder="social-publisher",
            # public_id אופציונלי — Cloudinary ייצור אוטומטית
        )

    secure_url = result["secure_url"]
    logger.info(f"Cloudinary URL: {secure_url}")
    return secure_url


def _get_suffix(mime_type: str) -> str:
    """ממיר MIME type לסיומת קובץ."""
    mapping = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/mpeg": ".mpeg",
        "video/webm": ".webm",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return mapping.get(mime_type, ".bin")
