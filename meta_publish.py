"""
meta_publish.py — פרסום ל-Instagram ו-Facebook דרך Graph API

Instagram: 2 קריאות (create container → publish)
Facebook: תמונה = /photos, וידאו = /videos
"""

import logging
import time

import requests

from config import (
    META_BASE_URL,
    IG_USER_ID,
    IG_ACCESS_TOKEN,
    FB_PAGE_ID,
    FB_PAGE_ACCESS_TOKEN,
    VIDEO_MIMES,
)

logger = logging.getLogger(__name__)

# Timeout לקריאות API
TIMEOUT_SHORT = 60   # תמונות
TIMEOUT_LONG = 180   # וידאו (העלאה + עיבוד)


# ═══════════════════════════════════════════════════════════════
#  Instagram — Feed (תמונה / וידאו)
# ═══════════════════════════════════════════════════════════════

def ig_publish_feed(
    cloud_url: str,
    caption: str,
    mime_type: str,
    post_type: str = "",
) -> str:
    """
    מפרסם פוסט Feed באינסטגרם.
    post_type: "reel" → media_type=REELS (גם לתמונות).
               ריק → תמונה רגילה או REELS לווידאו.
    מחזיר את ה-media ID של הפוסט שפורסם.
    """
    is_video = mime_type in VIDEO_MIMES

    # ── שלב 1: יצירת Container ──
    container_id = _ig_create_container(cloud_url, caption, is_video, post_type)

    # ── שלב 1.5: חכה לעיבוד (וידאו + תמונות) ──
    _ig_wait_for_container_ready(container_id, is_video=is_video)

    # ── שלב 2: פרסום ──
    result_id = _ig_publish_container(container_id)
    logger.info(f"Instagram published: {result_id}")
    return result_id


def _ig_create_container(
    cloud_url: str, caption: str, is_video: bool, post_type: str = ""
) -> str:
    """יצירת media container באינסטגרם."""
    url = f"{META_BASE_URL}/{IG_USER_ID}/media"
    data = {
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }

    if is_video:
        data["video_url"] = cloud_url
        data["media_type"] = "REELS"
    elif post_type.upper() == "REEL":
        # תמונה כ-Reel (carousel-style) — לא נפוץ, אבל נתמך
        data["image_url"] = cloud_url
        data["media_type"] = "REELS"
    else:
        data["image_url"] = cloud_url

    resp = requests.post(url, data=data, timeout=TIMEOUT_SHORT)
    if not resp.ok:
        logger.error(f"IG create container failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()

    container_id = resp.json()["id"]
    logger.info(f"IG container created: {container_id} (video={is_video})")
    return container_id


def _ig_wait_for_container_ready(
    container_id: str,
    is_video: bool = False,
    max_wait: int = 300,
    interval: int = 5,
) -> None:
    """
    ממתין עד שה-container מוכן לפרסום (סטטוס FINISHED).
    גם תמונות צריכות עיבוד — בד"כ 2-10 שניות, וידאו יותר.
    """
    url = f"{META_BASE_URL}/{container_id}"
    params = {
        "fields": "status_code",
        "access_token": IG_ACCESS_TOKEN,
    }

    elapsed = 0
    while elapsed < max_wait:
        resp = requests.get(url, params=params, timeout=TIMEOUT_SHORT)
        resp.raise_for_status()
        status = resp.json().get("status_code")

        logger.info(f"IG container {container_id}: status={status} ({elapsed}s)")

        if status == "FINISHED":
            return

        if status == "ERROR":
            error_msg = resp.json().get("status", "Unknown error")
            raise RuntimeError(
                f"Instagram container processing failed: {error_msg}"
            )

        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(
        f"Instagram container processing timed out after {max_wait}s "
        f"for container {container_id}"
    )


def _ig_publish_container(container_id: str) -> str:
    """פרסום container שמוכן."""
    url = f"{META_BASE_URL}/{IG_USER_ID}/media_publish"
    data = {
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN,
    }

    resp = requests.post(url, data=data, timeout=TIMEOUT_SHORT)
    if not resp.ok:
        logger.error(f"IG publish container failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()
    return resp.json()["id"]


# ═══════════════════════════════════════════════════════════════
#  Facebook Page — Feed (תמונה / וידאו)
# ═══════════════════════════════════════════════════════════════

def fb_publish_feed(
    cloud_url: str,
    caption: str,
    mime_type: str,
) -> str:
    """
    מפרסם פוסט Feed בעמוד פייסבוק.
    מחזיר post_id / video_id.
    """
    is_video = mime_type in VIDEO_MIMES

    if is_video:
        return _fb_publish_video(cloud_url, caption)
    else:
        return _fb_publish_photo(cloud_url, caption)


def _fb_publish_photo(cloud_url: str, caption: str) -> str:
    """פרסום תמונה בעמוד פייסבוק."""
    url = f"{META_BASE_URL}/{FB_PAGE_ID}/photos"
    data = {
        "url": cloud_url,
        "caption": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN,
    }

    resp = requests.post(url, data=data, timeout=TIMEOUT_SHORT)
    if not resp.ok:
        logger.error(f"FB publish photo failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()

    result = resp.json()
    result_id = result.get("post_id") or result.get("id")
    logger.info(f"FB photo published: {result_id}")
    return result_id


def _fb_publish_video(cloud_url: str, caption: str) -> str:
    """פרסום וידאו בעמוד פייסבוק."""
    url = f"{META_BASE_URL}/{FB_PAGE_ID}/videos"
    data = {
        "file_url": cloud_url,
        "description": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN,
        "published": "true",
    }

    resp = requests.post(url, data=data, timeout=TIMEOUT_LONG)
    if not resp.ok:
        logger.error(f"FB publish video failed ({resp.status_code}): {resp.text}")
        resp.raise_for_status()

    result_id = resp.json().get("id")
    logger.info(f"FB video published: {result_id}")
    return result_id
