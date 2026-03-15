"""
config.py — הגדרות סביבה וקבועים
"""

import os
import json
import urllib.parse
from zoneinfo import ZoneInfo

# ─── Timezone ────────────────────────────────────────────────
TZ_IL = ZoneInfo("Asia/Jerusalem")

# ─── Google ──────────────────────────────────────────────────
GOOGLE_SA_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]  # כל ה-JSON כמחרוזת
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SHEET_NAME = os.environ.get("SHEET_NAME", "Sheet1")

# ─── Meta / Facebook / Instagram ─────────────────────────────
META_API_VERSION = os.environ.get("META_API_VERSION", "v21.0")
META_BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"

IG_USER_ID = os.environ["IG_USER_ID"]
FB_PAGE_ID = os.environ["FB_PAGE_ID"]

# טוקנים — אפשר להשתמש באותו טוקן אם יש לו הרשאות לשניהם
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
FB_PAGE_ACCESS_TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]

# ─── Cloudinary ──────────────────────────────────────────────
# אפשרות 1 (מועדפת): CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
# אפשרות 2: שלושה משתנים נפרדים
_cloudinary_url = os.environ.get("CLOUDINARY_URL")
if _cloudinary_url:
    _parsed = urllib.parse.urlparse(_cloudinary_url)
    CLOUDINARY_CLOUD_NAME = _parsed.hostname
    CLOUDINARY_API_KEY = _parsed.username
    CLOUDINARY_API_SECRET = _parsed.password
else:
    CLOUDINARY_CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
    CLOUDINARY_API_KEY = os.environ["CLOUDINARY_API_KEY"]
    CLOUDINARY_API_SECRET = os.environ["CLOUDINARY_API_SECRET"]

# ─── Google Scopes ───────────────────────────────────────────
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ─── Sheet Column Names ─────────────────────────────────────
# אם תשנה שמות עמודות בטבלה, שנה רק פה
COL_ID = "id"
COL_STATUS = "status"
COL_NETWORK = "network"
COL_POST_TYPE = "post_type"
COL_PUBLISH_AT = "publish_at"
COL_CAPTION_IG = "caption_ig"
COL_CAPTION_FB = "caption_fb"
COL_DRIVE_FILE_ID = "drive_file_id"
COL_CLOUDINARY_URL = "cloudinary_url"
COL_RESULT = "result"
COL_ERROR = "error"

# ─── Status Values ───────────────────────────────────────────
STATUS_READY = "READY"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_POSTED = "POSTED"
STATUS_ERROR = "ERROR"

# ─── Network Values ─────────────────────────────────────────
NETWORK_IG = "IG"
NETWORK_FB = "FB"

# ─── Supported MIME types ────────────────────────────────────
VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/mpeg",
    "video/webm",
}
IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}


def get_google_sa_info() -> dict:
    """פרסור ה-Service Account JSON מתוך env var."""
    return json.loads(GOOGLE_SA_JSON)
