"""
notifications.py — שליחת התראות לטלגרם

שולח הודעות למפתח כשפוסט נכשל או כשיש בעיות מערכתיות.
דורש הגדרת TELEGRAM_BOT_TOKEN ו-TELEGRAM_CHAT_ID.
אם לא מוגדרים — ההתראות מושתקות (לא זורק שגיאה).
"""

import html
import logging
import os

import requests

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10  # seconds


def is_telegram_configured() -> bool:
    """בודק אם התראות טלגרם מוגדרות."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram(message: str) -> bool:
    """
    שולח הודעת טקסט לטלגרם.
    מחזיר True אם נשלח בהצלחה, False אחרת.
    לעולם לא זורק exception — שגיאת התראה לא צריכה לשבור את הפרסום.
    """
    if not is_telegram_configured():
        logger.debug("Telegram not configured — skipping notification")
        return False

    try:
        resp = requests.post(
            TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=TIMEOUT,
        )
        if resp.ok:
            logger.info("Telegram notification sent")
            return True
        else:
            logger.warning(f"Telegram send failed ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


def notify_publish_error(row_id: str, error_msg: str):
    """התראה על כשל בפרסום פוסט."""
    text = (
        f"<b>❌ שגיאת פרסום</b>\n"
        f"<b>פוסט:</b> #{html.escape(str(row_id))}\n"
        f"<b>שגיאה:</b> {html.escape(_truncate(error_msg, 500))}"
    )
    send_telegram(text)


def notify_partial_success(row_id: str, result: str, error_msg: str):
    """התראה על הצלחה חלקית (רשת אחת הצליחה, אחרת נכשלה)."""
    text = (
        f"<b>⚠️ הצלחה חלקית</b>\n"
        f"<b>פוסט:</b> #{html.escape(str(row_id))}\n"
        f"<b>הצליח:</b> {html.escape(result)}\n"
        f"<b>נכשל:</b> {html.escape(_truncate(error_msg, 400))}"
    )
    send_telegram(text)


def notify_health_issue(service: str, error_msg: str):
    """התראה על בעיה בשירות חיצוני."""
    text = (
        f"<b>🔴 בעיית חיבור</b>\n"
        f"<b>שירות:</b> {html.escape(service)}\n"
        f"<b>שגיאה:</b> {html.escape(_truncate(error_msg, 500))}"
    )
    send_telegram(text)


def notify_meta_api_version_expiry(version: str, expiry_date: str, days_left: int):
    """התראה על גרסת Meta API שעומדת לפוג."""
    if days_left <= 7:
        emoji = "🔴"
    elif days_left <= 30:
        emoji = "🟡"
    else:
        emoji = "🟢"
    text = (
        f"<b>{emoji} גרסת Meta API עומדת לפוג</b>\n"
        f"<b>גרסה:</b> {html.escape(version)}\n"
        f"<b>תפוגה:</b> {html.escape(expiry_date)}\n"
        f"<b>נותרו:</b> {days_left} ימים"
    )
    send_telegram(text)


def _truncate(text: str, max_len: int) -> str:
    """קיצור טקסט ארוך."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text
