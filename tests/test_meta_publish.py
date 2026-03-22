"""
test_meta_publish.py — בדיקות יחידה ל-meta_publish.py

מכסה: IG container creation (image vs video), IG wait loop,
       FB photo/video publishing, error handling.
"""

from unittest.mock import patch, MagicMock, call
import pytest

from meta_publish import (
    ig_publish_feed,
    fb_publish_feed,
    _ig_create_container,
    _ig_publish_container,
    _ig_wait_for_container_ready,
)


def _mock_response(json_data, status_code=200, ok=True):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


# ═══════════════════════════════════════════════════════════════
#  _ig_create_container
# ═══════════════════════════════════════════════════════════════

class TestIgCreateContainer:
    @patch("meta_publish.requests.post")
    def test_image_sends_image_url(self, mock_post):
        mock_post.return_value = _mock_response({"id": "container_1"})

        result = _ig_create_container("https://example.com/img.jpg", "caption", is_video=False)

        assert result == "container_1"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["image_url"] == "https://example.com/img.jpg"
        assert "video_url" not in call_data
        assert "media_type" not in call_data

    @patch("meta_publish.requests.post")
    def test_video_sends_video_url_and_reels(self, mock_post):
        mock_post.return_value = _mock_response({"id": "container_2"})

        result = _ig_create_container("https://example.com/vid.mp4", "caption", is_video=True)

        assert result == "container_2"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["video_url"] == "https://example.com/vid.mp4"
        assert call_data["media_type"] == "REELS"
        assert "image_url" not in call_data

    @patch("meta_publish.requests.post")
    def test_api_error_raises(self, mock_post):
        resp = _mock_response({"error": {"message": "bad token"}}, status_code=400, ok=False)
        resp.raise_for_status.side_effect = Exception("400 Bad Request")
        mock_post.return_value = resp

        with pytest.raises(Exception, match="400"):
            _ig_create_container("https://example.com/img.jpg", "cap", is_video=False)

    @patch("meta_publish.requests.post")
    def test_caption_with_special_chars(self, mock_post):
        """Captions with emoji, newlines, Hebrew should pass through."""
        mock_post.return_value = _mock_response({"id": "container_3"})
        caption = "שלום עולם! 🎉\nLine 2 & <special>"

        _ig_create_container("https://example.com/img.jpg", caption, is_video=False)

        call_data = mock_post.call_args[1]["data"]
        assert call_data["caption"] == caption

    @patch("meta_publish.requests.post")
    def test_empty_caption(self, mock_post):
        mock_post.return_value = _mock_response({"id": "container_4"})

        _ig_create_container("https://example.com/img.jpg", "", is_video=False)

        call_data = mock_post.call_args[1]["data"]
        assert call_data["caption"] == ""


# ═══════════════════════════════════════════════════════════════
#  _ig_wait_for_container_ready
# ═══════════════════════════════════════════════════════════════

class TestIgWaitForContainer:
    @patch("meta_publish.time.sleep")
    @patch("meta_publish.requests.get")
    def test_finished_immediately(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response({"status_code": "FINISHED"})

        _ig_wait_for_container_ready("container_1")

        mock_sleep.assert_not_called()

    @patch("meta_publish.time.sleep")
    @patch("meta_publish.requests.get")
    def test_finished_after_retries(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            _mock_response({"status_code": "IN_PROGRESS"}),
            _mock_response({"status_code": "IN_PROGRESS"}),
            _mock_response({"status_code": "FINISHED"}),
        ]

        _ig_wait_for_container_ready("container_1", interval=1)

        assert mock_sleep.call_count == 2

    @patch("meta_publish.time.sleep")
    @patch("meta_publish.requests.get")
    def test_error_status_raises(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response({
            "status_code": "ERROR",
            "status": "Media upload failed",
        })

        with pytest.raises(RuntimeError, match="Media upload failed"):
            _ig_wait_for_container_ready("container_1")

    @patch("meta_publish.time.sleep")
    @patch("meta_publish.requests.get")
    def test_timeout_raises(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response({"status_code": "IN_PROGRESS"})

        with pytest.raises(TimeoutError):
            _ig_wait_for_container_ready("container_1", max_wait=3, interval=1)


# ═══════════════════════════════════════════════════════════════
#  ig_publish_feed (full flow)
# ═══════════════════════════════════════════════════════════════

class TestIgPublishFeed:
    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_1")
    def test_image_full_flow(self, mock_create, mock_wait, mock_publish):
        result = ig_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg")

        assert result == "media_final"
        mock_create.assert_called_once_with("https://example.com/img.jpg", "cap", False)
        mock_wait.assert_called_once_with("container_1", is_video=False)
        mock_publish.assert_called_once_with("container_1")

    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_2")
    def test_video_full_flow(self, mock_create, mock_wait, mock_publish):
        result = ig_publish_feed("https://example.com/vid.mp4", "cap", "video/mp4")

        assert result == "media_final"
        mock_create.assert_called_once_with("https://example.com/vid.mp4", "cap", True)
        mock_wait.assert_called_once_with("container_2", is_video=True)


# ═══════════════════════════════════════════════════════════════
#  Facebook
# ═══════════════════════════════════════════════════════════════

class TestFbPublishFeed:
    @patch("meta_publish.requests.post")
    def test_photo_publishes_correctly(self, mock_post):
        mock_post.return_value = _mock_response({"post_id": "fb_post_1"})

        result = fb_publish_feed("https://example.com/img.jpg", "hello FB", "image/jpeg")

        assert result == "fb_post_1"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["url"] == "https://example.com/img.jpg"
        assert call_data["caption"] == "hello FB"

    @patch("meta_publish.requests.post")
    def test_video_publishes_correctly(self, mock_post):
        mock_post.return_value = _mock_response({"id": "fb_vid_1"})

        result = fb_publish_feed("https://example.com/vid.mp4", "video desc", "video/mp4")

        assert result == "fb_vid_1"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["file_url"] == "https://example.com/vid.mp4"
        assert call_data["description"] == "video desc"
        assert call_data["published"] == "true"

    @patch("meta_publish.requests.post")
    def test_fb_photo_api_error(self, mock_post):
        resp = _mock_response({}, status_code=403, ok=False)
        resp.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_post.return_value = resp

        with pytest.raises(Exception, match="403"):
            fb_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg")

    @patch("meta_publish.requests.post")
    def test_mov_detected_as_video(self, mock_post):
        """video/quicktime (MOV) should go through the video path."""
        mock_post.return_value = _mock_response({"id": "fb_vid_2"})

        fb_publish_feed("https://example.com/vid.mov", "cap", "video/quicktime")

        # Should have called /videos endpoint (file_url key)
        call_data = mock_post.call_args[1]["data"]
        assert "file_url" in call_data
