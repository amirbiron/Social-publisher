"""
test_main.py — בדיקות יחידה ל-main.py

מכסה: is_due, get_cell, process_row (הצלחה + שגיאות),
       main loop (סינון שורות), cleanup_old_cloudinary_assets.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call

import pytest

from config import TZ_IL, STATUS_READY, STATUS_POSTED, STATUS_ERROR, STATUS_IN_PROGRESS
from main import (
    is_due,
    get_cell,
    process_row,
    main,
    cleanup_old_cloudinary_assets,
    _CLOUDINARY_URL_RE,
)

# ─── Header fixture ──────────────────────────────────────────
HEADER = [
    "id", "status", "network", "post_type", "publish_at",
    "caption_ig", "caption_fb", "drive_file_id",
    "cloudinary_url", "result", "error",
]

NOW_UTC = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)


def _make_row(
    network="IG",
    post_type="FEED",
    drive_id="abc123",
    caption_ig="hello",
    caption_fb="",
    status=STATUS_READY,
):
    """Build a row matching HEADER order."""
    return [
        "1", status, network, post_type, "2026-03-22 10:00",
        caption_ig, caption_fb, drive_id, "", "", "",
    ]


# ═══════════════════════════════════════════════════════════════
#  is_due
# ═══════════════════════════════════════════════════════════════

class TestIsDue:
    def test_past_time_is_due(self):
        assert is_due("2026-03-22 10:00", NOW_UTC) is True

    def test_future_time_is_not_due(self):
        assert is_due("2026-03-23 20:00", NOW_UTC) is False

    def test_invalid_string_returns_false(self):
        assert is_due("not-a-date", NOW_UTC) is False

    def test_empty_string_returns_false(self):
        assert is_due("", NOW_UTC) is False

    def test_none_returns_false(self):
        assert is_due(None, NOW_UTC) is False


# ═══════════════════════════════════════════════════════════════
#  get_cell
# ═══════════════════════════════════════════════════════════════

class TestGetCell:
    def test_returns_value(self):
        row = _make_row()
        assert get_cell(row, HEADER, "network") == "IG"

    def test_missing_column_returns_default(self):
        row = ["1", "READY"]
        assert get_cell(row, HEADER, "nonexistent_col", "fallback") == "fallback"

    def test_short_row_returns_default(self):
        row = ["1", "READY"]
        assert get_cell(row, HEADER, "drive_file_id") == ""

    def test_empty_default(self):
        row = []
        assert get_cell(row, HEADER, "id") == ""


# ═══════════════════════════════════════════════════════════════
#  process_row — success paths
# ═══════════════════════════════════════════════════════════════

class TestProcessRowSuccess:
    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://res.cloudinary.com/x/image/upload/v1/social-publisher/abc.jpg")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-img", {"mimeType": "image/jpeg", "name": "pic.jpg"}))
    @patch("main.ig_publish_feed", return_value="media_111")
    def test_ig_image_feed(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        row = _make_row()
        process_row(row, HEADER, 2)

        mock_drive.assert_called_once_with("abc123")
        mock_cloud.assert_called_once_with(b"fake-img", "image/jpeg", "pic.jpg")
        mock_ig.assert_called_once_with(
            "https://res.cloudinary.com/x/image/upload/v1/social-publisher/abc.jpg",
            "hello",
            "image/jpeg",
            "FEED",
        )
        posted_call = mock_sheets.call_args_list[-1]
        assert posted_call[0][1]["status"] == STATUS_POSTED
        assert posted_call[0][1]["result"] == "media_111"

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/vid.mp4")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-vid", {"mimeType": "video/mp4", "name": "vid.mp4"}))
    @patch("main.fb_publish_feed", return_value="post_222")
    def test_fb_video_feed(self, mock_fb, mock_drive, mock_norm, mock_cloud, mock_sheets):
        row = _make_row(network="FB", caption_ig="", caption_fb="fb caption")
        process_row(row, HEADER, 3)

        mock_fb.assert_called_once_with(
            "https://example.com/vid.mp4",
            "fb caption",
            "video/mp4",
            "FEED",
        )
        posted_call = mock_sheets.call_args_list[-1]
        assert posted_call[0][1]["status"] == STATUS_POSTED

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/vid.mp4")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-vid", {"mimeType": "video/mp4", "name": "vid.mp4"}))
    @patch("main.fb_publish_feed", return_value="reel_333")
    def test_fb_video_reels(self, mock_fb, mock_drive, mock_norm, mock_cloud, mock_sheets):
        """post_type=REELS should be passed through to fb_publish_feed."""
        row = _make_row(network="FB", post_type="REELS", caption_ig="", caption_fb="reel caption")
        process_row(row, HEADER, 3)

        mock_fb.assert_called_once_with(
            "https://example.com/vid.mp4",
            "reel caption",
            "video/mp4",
            "REELS",
        )

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/vid.mp4")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-vid", {"mimeType": "video/mp4", "name": "vid.mp4"}))
    @patch("main.ig_publish_feed", return_value="media_444")
    def test_ig_video_reels(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        """post_type=REELS on IG should pass through."""
        row = _make_row(post_type="REELS")
        process_row(row, HEADER, 2)

        mock_ig.assert_called_once_with(
            "https://example.com/vid.mp4",
            "hello",
            "video/mp4",
            "REELS",
        )

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/img.jpg")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-img", {"mimeType": "image/jpeg", "name": "img.jpg"}))
    @patch("main.ig_publish_feed", return_value="media_555")
    def test_empty_post_type_defaults_to_feed(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        """If post_type column is empty, should default to FEED."""
        row = _make_row(post_type="")
        process_row(row, HEADER, 2)

        mock_ig.assert_called_once()
        assert mock_ig.call_args[0][3] == "FEED"

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/img.jpg")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"fake-img", {"mimeType": "image/jpeg", "name": "img.jpg"}))
    @patch("main.ig_publish_feed", return_value="media_333")
    def test_caption_fallback_ig_uses_fb_if_empty(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        """If caption_ig is empty, should fallback to caption_fb."""
        row = _make_row(caption_ig="", caption_fb="fallback text")
        process_row(row, HEADER, 2)

        mock_ig.assert_called_once()
        assert mock_ig.call_args[0][1] == "fallback text"


# ═══════════════════════════════════════════════════════════════
#  process_row — error handling
# ═══════════════════════════════════════════════════════════════

class TestProcessRowErrors:
    @patch("main.sheets_update_cells")
    def test_missing_drive_file_id(self, mock_sheets):
        row = _make_row(drive_id="")
        process_row(row, HEADER, 2)

        mock_sheets.assert_called_once()
        assert mock_sheets.call_args[0][1]["status"] == STATUS_ERROR
        assert "Missing drive_file_id" in mock_sheets.call_args[0][1]["error"]

    @patch("main.sheets_update_cells")
    def test_unknown_network(self, mock_sheets):
        row = _make_row(network="TIKTOK")
        process_row(row, HEADER, 2)

        assert mock_sheets.call_args[0][1]["status"] == STATUS_ERROR
        assert "Unknown network" in mock_sheets.call_args[0][1]["error"]

    @patch("main.sheets_update_cells")
    @patch("main.drive_download_with_metadata", side_effect=Exception("Drive API error"))
    def test_drive_error_marks_error(self, mock_drive, mock_sheets):
        row = _make_row()
        process_row(row, HEADER, 2)

        last_call = mock_sheets.call_args_list[-1]
        assert last_call[0][1]["status"] == STATUS_ERROR
        assert "Drive API error" in last_call[0][1]["error"]

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/img.jpg")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"img", {"mimeType": "image/jpeg", "name": "x.jpg"}))
    @patch("main.ig_publish_feed", side_effect=Exception("API rate limit"))
    def test_publish_error_marks_error(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        row = _make_row()
        process_row(row, HEADER, 2)

        last_call = mock_sheets.call_args_list[-1]
        assert last_call[0][1]["status"] == STATUS_ERROR
        assert "rate limit" in last_call[0][1]["error"]

    @patch("main.sheets_update_cells")
    @patch("main.upload_to_cloudinary", return_value="https://example.com/img.jpg")
    @patch("main.normalize_media", side_effect=lambda b, m, n, p: (b, m, n))
    @patch("main.drive_download_with_metadata", return_value=(b"img", {"mimeType": "image/jpeg", "name": "x.jpg"}))
    @patch("main.ig_publish_feed", side_effect=Exception("x" * 600))
    def test_long_error_message_truncated(self, mock_ig, mock_drive, mock_norm, mock_cloud, mock_sheets):
        row = _make_row()
        process_row(row, HEADER, 2)

        last_call = mock_sheets.call_args_list[-1]
        error_msg = last_call[0][1]["error"]
        assert len(error_msg) <= 500


# ═══════════════════════════════════════════════════════════════
#  main() — row filtering
# ═══════════════════════════════════════════════════════════════

class TestMainLoop:
    @patch("main.cleanup_old_cloudinary_assets", return_value=0)
    @patch("main.process_row")
    @patch("main.sheets_read_all_rows")
    def test_only_ready_rows_processed(self, mock_read, mock_process, mock_cleanup):
        mock_read.return_value = (
            HEADER,
            [
                # row 2: READY + due → should process
                _make_row(),
                # row 3: POSTED → skip
                _make_row(status="POSTED"),
                # row 4: READY + future → skip (we override publish_at below)
                ["3", "READY", "IG", "FEED", "2099-01-01 10:00", "cap", "", "abc", "", "", ""],
                # row 5: READY + due → should process
                _make_row(network="FB", caption_ig="", caption_fb="cap"),
            ],
        )

        main()

        assert mock_process.call_count == 2
        assert mock_process.call_args_list[0][0][2] == 2
        assert mock_process.call_args_list[1][0][2] == 5

    @patch("main.cleanup_old_cloudinary_assets", return_value=0)
    @patch("main.process_row")
    @patch("main.sheets_read_all_rows")
    def test_empty_sheet(self, mock_read, mock_process, mock_cleanup):
        mock_read.return_value = ([], [])
        main()
        mock_process.assert_not_called()

    @patch("main.cleanup_old_cloudinary_assets", return_value=0)
    @patch("main.process_row", side_effect=Exception("boom"))
    @patch("main.sheets_read_all_rows")
    def test_process_row_exception_propagates(self, mock_read, mock_process, mock_cleanup):
        """main() does not catch exceptions from process_row — if one leaks
        past process_row's internal try/except, the run aborts."""
        mock_read.return_value = (
            HEADER,
            [_make_row()],
        )
        with pytest.raises(Exception, match="boom"):
            main()


# ═══════════════════════════════════════════════════════════════
#  Cloudinary URL regex
# ═══════════════════════════════════════════════════════════════

class TestCloudinaryUrlRegex:
    def test_image_url(self):
        url = "https://res.cloudinary.com/mycloud/image/upload/v123/social-publisher/abc.jpg"
        m = _CLOUDINARY_URL_RE.match(url)
        assert m
        assert m.group("rtype") == "image"
        assert m.group("pid") == "social-publisher/abc"

    def test_video_url(self):
        url = "https://res.cloudinary.com/mycloud/video/upload/v999/social-publisher/vid.mp4"
        m = _CLOUDINARY_URL_RE.match(url)
        assert m
        assert m.group("rtype") == "video"
        assert m.group("pid") == "social-publisher/vid"

    def test_invalid_url(self):
        assert _CLOUDINARY_URL_RE.match("https://example.com/foo.jpg") is None


# ═══════════════════════════════════════════════════════════════
#  cleanup_old_cloudinary_assets
# ═══════════════════════════════════════════════════════════════

class TestCleanup:
    @patch("main.sheets_update_cells")
    @patch("main.delete_from_cloudinary", return_value=True)
    def test_deletes_old_posted_assets(self, mock_delete, mock_sheets):
        rows = [
            ["1", "POSTED", "IG", "FEED", "2026-01-01 10:00", "", "",
             "abc", "https://res.cloudinary.com/x/image/upload/v1/social-publisher/old.jpg", "r1", ""],
        ]
        deleted = cleanup_old_cloudinary_assets(HEADER, rows, NOW_UTC)
        assert deleted == 1
        mock_delete.assert_called_once_with("social-publisher/old", resource_type="image")

    @patch("main.delete_from_cloudinary")
    def test_skips_recent_posts(self, mock_delete):
        rows = [
            ["1", "POSTED", "IG", "FEED", "2026-03-22 10:00", "", "",
             "abc", "https://res.cloudinary.com/x/image/upload/v1/social-publisher/new.jpg", "r1", ""],
        ]
        deleted = cleanup_old_cloudinary_assets(HEADER, rows, NOW_UTC)
        assert deleted == 0
        mock_delete.assert_not_called()

    @patch("main.delete_from_cloudinary")
    def test_skips_non_posted_rows(self, mock_delete):
        rows = [
            ["1", "READY", "IG", "FEED", "2026-01-01 10:00", "", "",
             "abc", "https://res.cloudinary.com/x/image/upload/v1/social-publisher/x.jpg", "", ""],
        ]
        deleted = cleanup_old_cloudinary_assets(HEADER, rows, NOW_UTC)
        assert deleted == 0
