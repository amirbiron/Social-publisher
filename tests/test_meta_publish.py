"""
test_meta_publish.py — בדיקות יחידה ל-meta_publish.py

מכסה: IG container creation (image vs video), IG wait loop,
       FB photo/video/reel publishing, post_type routing, error handling.
"""

from unittest.mock import patch, MagicMock, call
import pytest

from meta_publish import (
    ig_publish_feed,
    fb_publish_feed,
    _ig_create_container,
    _ig_publish_container,
    _ig_wait_for_container_ready,
    _fb_publish_reel,
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
#  ig_publish_feed (full flow with post_type)
# ═══════════════════════════════════════════════════════════════

class TestIgPublishFeed:
    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_1")
    def test_image_feed(self, mock_create, mock_wait, mock_publish):
        result = ig_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg", "FEED")

        assert result == "media_final"
        mock_create.assert_called_once_with("https://example.com/img.jpg", "cap", False)
        mock_wait.assert_called_once_with("container_1", is_video=False)

    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_2")
    def test_video_feed_uses_reels_anyway(self, mock_create, mock_wait, mock_publish):
        """Even with post_type=FEED, video on IG must use REELS (API limitation)."""
        result = ig_publish_feed("https://example.com/vid.mp4", "cap", "video/mp4", "FEED")

        assert result == "media_final"
        # is_video=True → use_reels=True regardless of post_type
        mock_create.assert_called_once_with("https://example.com/vid.mp4", "cap", True)
        mock_wait.assert_called_once_with("container_2", is_video=True)

    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_3")
    def test_video_reels(self, mock_create, mock_wait, mock_publish):
        result = ig_publish_feed("https://example.com/vid.mp4", "cap", "video/mp4", "REELS")

        assert result == "media_final"
        mock_create.assert_called_once_with("https://example.com/vid.mp4", "cap", True)

    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_4")
    def test_image_reels_uses_reels_container(self, mock_create, mock_wait, mock_publish):
        """post_type=REELS with image → still sends as REELS container."""
        result = ig_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg", "REELS")

        assert result == "media_final"
        mock_create.assert_called_once_with("https://example.com/img.jpg", "cap", True)

    @patch("meta_publish._ig_publish_container", return_value="media_final")
    @patch("meta_publish._ig_wait_for_container_ready")
    @patch("meta_publish._ig_create_container", return_value="container_5")
    def test_default_post_type_is_feed(self, mock_create, mock_wait, mock_publish):
        """If post_type is not provided, defaults to FEED."""
        ig_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg")

        mock_create.assert_called_once_with("https://example.com/img.jpg", "cap", False)


# ═══════════════════════════════════════════════════════════════
#  Facebook — post_type routing
# ═══════════════════════════════════════════════════════════════

class TestFbPublishFeed:
    @patch("meta_publish.requests.post")
    def test_photo_feed(self, mock_post):
        mock_post.return_value = _mock_response({"post_id": "fb_post_1"})

        result = fb_publish_feed("https://example.com/img.jpg", "hello FB", "image/jpeg", "FEED")

        assert result == "fb_post_1"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["url"] == "https://example.com/img.jpg"
        assert call_data["caption"] == "hello FB"

    @patch("meta_publish.requests.post")
    def test_video_feed(self, mock_post):
        mock_post.return_value = _mock_response({"id": "fb_vid_1"})

        result = fb_publish_feed("https://example.com/vid.mp4", "video desc", "video/mp4", "FEED")

        assert result == "fb_vid_1"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["file_url"] == "https://example.com/vid.mp4"
        assert call_data["description"] == "video desc"
        assert call_data["published"] == "true"

    @patch("meta_publish.requests.post")
    def test_video_reels_uses_video_reels_endpoint(self, mock_post):
        """post_type=REELS + video should use /{page_id}/video_reels."""
        mock_post.return_value = _mock_response({"id": "fb_reel_1"})

        result = fb_publish_feed("https://example.com/vid.mp4", "reel desc", "video/mp4", "REELS")

        assert result == "fb_reel_1"
        # Check endpoint
        call_url = mock_post.call_args[0][0]
        assert "/video_reels" in call_url
        call_data = mock_post.call_args[1]["data"]
        assert call_data["video_url"] == "https://example.com/vid.mp4"
        assert call_data["description"] == "reel desc"

    @patch("meta_publish.requests.post")
    def test_photo_reels_falls_back_to_photo(self, mock_post):
        """post_type=REELS + image → can't make a reel from image, falls back to photo."""
        mock_post.return_value = _mock_response({"post_id": "fb_post_2"})

        result = fb_publish_feed("https://example.com/img.jpg", "cap", "image/jpeg", "REELS")

        assert result == "fb_post_2"
        call_data = mock_post.call_args[1]["data"]
        # Should use photo endpoint (url key, not video_url)
        assert call_data["url"] == "https://example.com/img.jpg"

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

        call_data = mock_post.call_args[1]["data"]
        assert "file_url" in call_data

    @patch("meta_publish.requests.post")
    def test_default_post_type_is_feed(self, mock_post):
        """If post_type not provided, defaults to FEED (regular video, not reel)."""
        mock_post.return_value = _mock_response({"id": "fb_vid_3"})

        fb_publish_feed("https://example.com/vid.mp4", "cap", "video/mp4")

        call_data = mock_post.call_args[1]["data"]
        # Should use regular video endpoint (file_url, not video_url)
        assert "file_url" in call_data


# ═══════════════════════════════════════════════════════════════
#  _fb_publish_reel (direct)
# ═══════════════════════════════════════════════════════════════

class TestFbPublishReel:
    @patch("meta_publish.requests.post")
    def test_reel_endpoint_and_params(self, mock_post):
        mock_post.return_value = _mock_response({"id": "reel_99"})

        result = _fb_publish_reel("https://example.com/vid.mp4", "reel caption")

        assert result == "reel_99"
        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/video_reels")
        call_data = mock_post.call_args[1]["data"]
        assert call_data["video_url"] == "https://example.com/vid.mp4"
        assert call_data["description"] == "reel caption"

    @patch("meta_publish.requests.post")
    def test_reel_api_error(self, mock_post):
        resp = _mock_response({}, status_code=400, ok=False)
        resp.raise_for_status.side_effect = Exception("400 Bad Request")
        mock_post.return_value = resp

        with pytest.raises(Exception, match="400"):
            _fb_publish_reel("https://example.com/vid.mp4", "cap")
