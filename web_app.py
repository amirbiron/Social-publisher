"""
web_app.py — פאנל ווב לניהול פוסטים ברשתות חברתיות

Flask app שמתחבר ל-Google Sheets ו-Google Drive,
ומספק ממשק פשוט ללקוחה לניהול הפוסטים.
"""

import logging
import os
import sys
from datetime import datetime, timezone

from dateutil import parser as dtparser
from flask import Flask, jsonify, render_template, request

from config import (
    TZ_IL,
    COL_ID,
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
    STATUS_POSTED,
    STATUS_ERROR,
    STATUS_IN_PROGRESS,
    NETWORK_IG,
    NETWORK_FB,
    NETWORK_BOTH,
    POST_TYPE_FEED,
    POST_TYPE_REELS,
)
from google_api import (
    sheets_read_all_rows,
    sheets_update_cells,
    sheets_append_row,
    sheets_delete_row,
    col_letter_from_header,
    drive_list_folder,
    drive_get_file_metadata,
)

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("web-panel")

# ─── Flask App ───────────────────────────────────────────────
app = Flask(__name__)

# Drive folder ID (root folder for media files)
DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")

# Expected column order in the sheet
SHEET_COLUMNS = [
    COL_ID, COL_STATUS, COL_NETWORK, COL_POST_TYPE,
    COL_PUBLISH_AT, COL_CAPTION_IG, COL_CAPTION_FB,
    COL_DRIVE_FILE_ID, COL_CLOUDINARY_URL, COL_RESULT, COL_ERROR,
]


# ═══════════════════════════════════════════════════════════════
#  Pages
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════
#  API — Posts (Google Sheets)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/posts", methods=["GET"])
def api_get_posts():
    """מחזיר את כל הפוסטים מהטבלה."""
    try:
        header, rows = sheets_read_all_rows()
        if not header:
            return jsonify({"posts": [], "header": []})

        posts = []
        for i, row in enumerate(rows, start=2):
            post = {"_row": i}
            for j, col_name in enumerate(header):
                post[col_name] = row[j] if j < len(row) else ""
            posts.append(post)

        return jsonify({"posts": posts, "header": header})

    except Exception as e:
        logger.error(f"Error fetching posts: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/posts", methods=["POST"])
def api_create_post():
    """יצירת פוסט חדש (שורה חדשה בטבלה)."""
    try:
        data = request.json
        header, rows = sheets_read_all_rows()

        if not header:
            return jsonify({"error": "Sheet has no header"}), 400

        # Generate next ID
        max_id = 0
        for row in rows:
            try:
                idx = header.index(COL_ID)
                val = int(row[idx]) if idx < len(row) else 0
                max_id = max(max_id, val)
            except (ValueError, IndexError):
                pass
        next_id = str(max_id + 1)

        # Build row values in header order
        row_values = []
        for col_name in header:
            if col_name == COL_ID:
                row_values.append(next_id)
            elif col_name == COL_STATUS:
                row_values.append(STATUS_READY)
            else:
                row_values.append(data.get(col_name, ""))

        sheets_append_row(row_values)
        logger.info(f"Created post ID {next_id}")

        return jsonify({"success": True, "id": next_id})

    except Exception as e:
        logger.error(f"Error creating post: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/posts/<int:row_number>", methods=["PUT"])
def api_update_post(row_number):
    """עדכון פוסט קיים."""
    try:
        data = request.json
        header, _ = sheets_read_all_rows()

        if not header:
            return jsonify({"error": "Sheet has no header"}), 400

        # Only allow updating specific fields
        allowed_fields = {
            COL_NETWORK, COL_POST_TYPE, COL_PUBLISH_AT,
            COL_CAPTION_IG, COL_CAPTION_FB, COL_DRIVE_FILE_ID,
            COL_STATUS,
        }

        updates = {}
        for key, value in data.items():
            if key in allowed_fields:
                updates[key] = value

        if updates:
            sheets_update_cells(row_number, updates, header)
            logger.info(f"Updated row {row_number}: {list(updates.keys())}")

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error updating post: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/posts/<int:row_number>", methods=["DELETE"])
def api_delete_post(row_number):
    """מחיקת פוסט (שורה מהטבלה)."""
    try:
        sheets_delete_row(row_number)
        logger.info(f"Deleted row {row_number}")
        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error deleting post: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
#  API — Google Drive
# ═══════════════════════════════════════════════════════════════

@app.route("/api/drive/files", methods=["GET"])
def api_drive_files():
    """מחזיר קבצים מתיקיית Drive."""
    try:
        folder_id = request.args.get("folder_id", DRIVE_FOLDER_ID)
        if not folder_id:
            return jsonify({"error": "No folder ID configured"}), 400

        page_token = request.args.get("page_token")
        result = drive_list_folder(folder_id, page_token)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error listing Drive files: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/drive/file/<file_id>", methods=["GET"])
def api_drive_file_meta(file_id):
    """מחזיר metadata של קובץ מ-Drive."""
    try:
        metadata = drive_get_file_metadata(file_id)
        return jsonify(metadata)

    except Exception as e:
        logger.error(f"Error fetching file metadata: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
#  API — Config (public, non-sensitive)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def api_config():
    """מחזיר הגדרות ציבוריות לפרונטאנד."""
    return jsonify({
        "driveFolderId": DRIVE_FOLDER_ID,
        "columns": SHEET_COLUMNS,
        "statuses": [STATUS_READY, STATUS_IN_PROGRESS, STATUS_POSTED, STATUS_ERROR],
        "networks": [NETWORK_IG, NETWORK_FB, NETWORK_BOTH],
        "postTypes": [POST_TYPE_FEED, POST_TYPE_REELS],
    })


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
