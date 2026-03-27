# מסמך אפיון: Multi-Channel Publisher

> **תאריך:** 27.03.2026
> **סטטוס:** טיוטה מעודכנת לאחר סבב ביקורת
> **פרויקט בסיס:** Social Publisher (קיים ופעיל)

---

## 1. רקע ומצב קיים

### מה קיים היום
מערכת **Social Publisher** — פאנל ווב (Flask + Google Sheets) שמנהל ומפרסם פוסטים ל-**Facebook** ו-**Instagram** דרך Meta Graph API.

**זרימה נוכחית:**
```
Google Sheets (תור פוסטים)
  → Google Drive (מדיה)
    → Cloudinary (CDN)
      → Meta Graph API (IG / FB)
```

**טכנולוגיות:**
- **Backend:** Python 3.12, Flask, Gunicorn
- **מסד נתונים:** Google Sheets (מסמך טבלאי כ-DB)
- **אחסון מדיה:** Google Drive → Cloudinary
- **API פרסום:** Meta Graph API (v21.0)
- **התראות:** Telegram Bot
- **דיפלוי:** Render (Cron Job + Web Service)
- **עיבוד מדיה:** Pillow (נרמול תמונות/וידאו)

### מערכת הלקוח הקיימת (חיצונית)
פאנל נפרד (Claude + Supabase) שמייצר תוכן באמצעות AI:
- המשתמש מכניס נושא + יעד רשת
- המערכת מייצרת תוכן מבוסס לוגיקה, סגנון לקוח, ונתוני מחקר
- **הפלט יוצא ל-Google Sheets** בפורמט מובנה

---

## 2. מטרת הפרויקט

בניית **Multi-Channel Publisher** — הרחבה של המערכת הקיימת כך ש:

1. **UI אחד אחיד** — ממשק אחד לניהול כל ערוצי הפרסום
2. **חיבור נפרד לכל פלטפורמה** — כל ערוץ עם API, קרדנשיאלס וסטטוס עצמאי
3. **סטטוס נפרד לכל ערוץ** — פוסט אחד יכול להצליח ב-FB ולהיכשל ב-Google Business
4. **ארכיטקטורה מודולרית** — הוספת ערוץ חדש = הוספת מודול, בלי לשנות את המבנה
5. **חיבור אוטומטי למערכת הקיימת** — קליטה ישירה מה-Google Sheets שמייצרת מערכת ה-AI, עם אפשרות גם להתערבות ידנית

---

## 3. ערוצי פרסום — שלב ראשון

| ערוץ | סטטוס | API |
|------|--------|-----|
| Instagram | קיים ✅ | Meta Graph API |
| Facebook Page | קיים ✅ | Meta Graph API |
| Google Business Profile | **חדש** 🆕 | Google Business Profile API |

### Google Business Profile API — סקירה
- **API:** Google My Business API / Business Profile API
- **יכולות:** פוסטים (STANDARD, EVENT, OFFER), תמונות, עדכונים
- **אימות:** OAuth 2.0 (ברירת מחדל). Service Account — רק לאחר POC שמוכיח תאימות עם החשבון העסקי הספציפי
- **מגבלות:** המכסות תלויות באישור הפרויקט ובהגדרות Google (למשל 300 QPM לחלק מה-APIs). יש לאמת אותן בפועל מול הפרויקט לפני עלייה לאוויר. פוסט מוגבל ל-1,500 תווים
- **סוגי פוסטים ב-API:** `STANDARD` (טקסט+תמונה), `EVENT` (אירוע עם תאריכים), `OFFER` (הנחה עם קופון)
- **הערה חשובה:** ב-UI נציג "עדכון" למשתמש, אבל בקוד נמפה ל-`STANDARD` שהוא הסוג הרשמי ב-API. אין סוג `UPDATE` ב-GBP API

---

## 4. ארכיטקטורה — שכבת ערוצים (Channel Layer)

### 4.1 עיקרון: Channel Interface

כל ערוץ פרסום מממש ממשק אחיד:

```python
# channels/base.py

class PublishResult:
    """תוצאת פרסום לערוץ בודד"""
    channel: str          # "IG", "FB", "GBP"
    success: bool
    post_id: str | None   # מזהה הפוסט בפלטפורמה
    error: str | None

class BaseChannel:
    """ממשק בסיס לכל ערוץ פרסום"""

    CHANNEL_ID: str               # מזהה ייחודי: "IG", "FB", "GBP"
    CHANNEL_NAME: str             # שם תצוגה: "Instagram", "Google Business"
    SUPPORTED_POST_TYPES: list    # ["FEED", "REELS"] / ["STANDARD", "EVENT"]
    SUPPORTED_MEDIA_TYPES: list   # ["image", "video"] / ["image"]

    def validate(self, post_data: dict) -> list[str]:
        """בדיקת תקינות לפני פרסום — מחזיר רשימת שגיאות (ריקה = תקין)"""

    def publish(self, post_data: dict) -> PublishResult:
        """פרסום בפועל — מחזיר תוצאה"""

    def get_caption_column(self) -> str:
        """שם עמודת הכיתוב בטבלה"""
```

### 4.2 מבנה תיקיות מוצע

```
Social-publisher/
├── channels/
│   ├── __init__.py
│   ├── base.py              # BaseChannel + PublishResult
│   ├── registry.py          # רישום והפעלת ערוצים
│   ├── meta_instagram.py    # IG — מעטפת ל-meta_publish.py הקיים
│   ├── meta_facebook.py     # FB — מעטפת ל-meta_publish.py הקיים
│   └── google_business.py   # GBP — חדש
├── main.py                  # עדכון — שימוש ב-registry
├── web_app.py               # עדכון — UI מרובה ערוצים
├── meta_publish.py          # ← נשאר כמו שהוא (backward compatible)
├── google_api.py            # ← נשאר + הוספת GBP functions
├── ...
```

### 4.3 Channel Registry — רישום ערוצים

```python
# channels/registry.py

class ChannelRegistry:
    """מנהל ערוצים — נקודת כניסה מרכזית"""

    _channels: dict[str, BaseChannel] = {}

    def register(self, channel: BaseChannel):
        """רישום ערוץ חדש"""

    def get(self, channel_id: str) -> BaseChannel:
        """קבלת ערוץ לפי מזהה"""

    def get_all(self) -> list[BaseChannel]:
        """כל הערוצים הרשומים"""

    def publish_to_channels(
        self,
        post_data: dict,
        target_channels: list[str]
    ) -> dict[str, PublishResult]:
        """
        פרסום לרשימת ערוצים.
        מחזיר: {"IG": PublishResult(...), "FB": PublishResult(...), "GBP": PublishResult(...)}
        """
```

**יתרון:** להוסיף ערוץ חדש בעתיד = ליצור קובץ channel חדש + לרשום אותו ב-registry.

---

## 5. מבנה הנתונים — Google Sheets

### 5.1 שינויים בטבלה

**עמודות חדשות:**

| עמודה | תיאור | דוגמה |
|-------|--------|--------|
| `network` | **עדכון** — תמיכה בערוצים נוספים | `IG+FB+GBP`, `GBP`, `IG+GBP` |
| `caption_gbp` | כיתוב ל-Google Business | "עדכון חדש מהעסק..." |
| `gbp_post_type` | סוג פוסט ב-GBP | `STANDARD` / `EVENT` / `OFFER` |
| `result_detail` | תוצאה מפורטת לכל ערוץ | `IG:OK:123 \| FB:OK:456 \| GBP:ERR:timeout` |
| `source` | מקור הפוסט | `manual` / `auto` / `ai-panel` |

### 5.2 פורמט Network מורחב

```
# ערוץ בודד
IG
FB
GBP

# שילובים
IG+FB          (קיים)
IG+GBP
FB+GBP
IG+FB+GBP     (כל הערוצים)
ALL            (קיצור ל-כל הערוצים הרשומים)
```

### 5.3 פורמט תוצאה מפורט

**פתרון MVP — מחרוזת `result_detail`:**
```
# עמודת result_detail
IG:POSTED:17841405822953 | FB:POSTED:615273820 | GBP:ERROR:quota_exceeded

# עמודת status — לוגיקה מעודכנת
POSTED       → כל הערוצים הצליחו
PARTIAL      → חלק הצליחו, חלק נכשלו (חדש!)
ERROR        → כל הערוצים נכשלו
```

> **הערה:** פורמט `result_detail` כמחרוזת מספיק ל-MVP, אך לא מתאים לסינון, retry לפי ערוץ, או ניתוח שגיאות בדוחות.
> **שדרוג מומלץ (post-MVP):** הוספת Sheet נפרד בשם `deliveries` — כל שורה = ניסיון פרסום לערוץ בודד, עם עמודות: `post_id`, `channel`, `status`, `platform_id`, `error`, `attempt`, `timestamp`.

### 5.4 סטטוסים פנימיים — מנגנון מניעת פרסום כפול

כדי למנוע מצב שבו שני סבבי Cron קוראים את אותה שורה בו-זמנית:

```
READY        → ממתין לפרסום
PROCESSING   → נלקח לטיפול (נעול)
POSTED       → כל הערוצים הצליחו
PARTIAL      → חלק הצליחו
ERROR        → כל הערוצים נכשלו
```

**עמודות נדרשות:**

| עמודה | תיאור | דוגמה |
|-------|--------|--------|
| `locked_at` | timestamp של נעילה | `2026-03-27T18:00:05Z` |
| `run_id` | מזהה הריצה שנעלה את השורה | `run_abc123` |
| `retry_count` | מספר ניסיונות | `0`, `1`, `2` |

**זרימה:**
1. Cron קורא שורות `READY` שהגיע זמנן
2. מעדכן מיידית ל-`PROCESSING` + `locked_at` + `run_id`
3. מפרסם לערוצים
4. מעדכן ל-`POSTED` / `PARTIAL` / `ERROR`
5. שורה שנשארת `PROCESSING` מעל X דקות → timeout, חוזרת ל-`READY` (עם הגדלת `retry_count`)

---

## 6. חיבור למערכת ה-AI הקיימת

### 6.1 תרחיש: קליטה אוטומטית מ-Google Sheets

```
┌──────────────────┐     Google Sheets      ┌──────────────────────┐
│  AI Content      │  ──── כותב ל- ────►   │  Multi-Channel       │
│  Generator       │     טבלה מובנית        │  Publisher           │
│  (Claude+Supa)   │                        │  (קורא ומפרסם)       │
└──────────────────┘                        └──────────────────────┘
```

**איך זה עובד:**
1. מערכת ה-AI כותבת שורה ל-Google Sheets עם `status=READY`
2. ה-Publisher (Cron Job) קורא שורות READY שהגיע זמנן
3. מפרסם לערוצים שהוגדרו בעמודת `network`
4. מעדכן סטטוס + תוצאה

### 6.2 חוזה נתונים (Data Contract) מול מערכת ה-AI

| שדה | חובה? | דוגמה | הערות |
|---|---|---|---|
| `status` | כן | `READY` | רק ערכים מותרים: `READY`, `DRAFT` |
| `network` | כן | `IG+FB+GBP` | או `ALL` |
| `scheduled_time` | כן | `2026-03-27 18:00` | timezone מוסכם (Asia/Jerusalem) |
| `caption` | כן | "טקסט ברירת מחדל..." | caption כללי — fallback לכל ערוץ |
| `caption_ig` | לא | "..." | אם קיים — עוקף את `caption` עבור IG |
| `caption_fb` | לא | "..." | אם קיים — עוקף את `caption` עבור FB |
| `caption_gbp` | מותנה | "..." | חובה אם GBP ברשימת הערוצים ואין `caption` כללי |
| `media_url` / `drive_file_id` | מותנה | `https://...` | לפחות asset אחד לפוסט עם מדיה |
| `gbp_post_type` | מותנה | `STANDARD` | חובה אם GBP ברשימת הערוצים |
| `source` | כן | `ai-panel` | ערכים סגורים: `manual`, `auto`, `ai-panel` |

**לוגיקת fallback לכיתובים:**
1. אם יש `caption_{channel}` → משתמשים בו
2. אחרת אם יש `caption` כללי → משתמשים בו
3. אחרת → validation error (הפוסט לא יצא לפרסום)

### 6.3 תרחיש: התערבות ידנית

הפאנל החדש תומך גם בעבודה ידנית מלאה:
- יצירת פוסט חדש ידנית
- עריכת פוסט שנוצר אוטומטית (לפני פרסום)
- שינוי ערוצי יעד
- פרסום מיידי (Publish Now)
- צפייה בתוצאות ושגיאות לכל ערוץ

---

## 7. שינויים ב-UI (פאנל ווב)

### 7.1 בחירת ערוצים

```
┌─────────────────────────────────────────────┐
│  ערוצי פרסום:                               │
│  [✓] Instagram   [✓] Facebook   [✓] GBP    │
│                                             │
│  כיתוב Instagram: ___________________       │
│  כיתוב Facebook:  ___________________       │
│  כיתוב GBP:       ___________________       │
│                                             │
│  סוג פוסט GBP: [עדכון (STANDARD) ▾]          │
└─────────────────────────────────────────────┘
```

### 7.2 תצוגת סטטוס מרובה ערוצים

כל פוסט מציג סטטוס לכל ערוץ בנפרד:

```
┌─────────────────────────────────────────────┐
│  פוסט #42 — "עדכון שבועי"                   │
│                                             │
│  IG  ✅ פורסם (ID: 17841405822953)          │
│  FB  ✅ פורסם (ID: 615273820)               │
│  GBP ❌ שגיאה: quota_exceeded               │
│                                             │
│  [נסה שוב GBP]  [ערוך]  [מחק]              │
└─────────────────────────────────────────────┘
```

### 7.3 פילטר לפי ערוץ

```
סינון: [הכל ▾] [IG] [FB] [GBP] [שגיאות בלבד]
```

### 7.4 ולידציה לפי יכולות ערוץ

לא כל ערוץ תומך באותן יכולות. ה-UI צריך להתאים את עצמו בזמן אמת:

| ערוץ | תמונה | וידאו | Reels | Stories | Carousel |
|------|--------|--------|-------|---------|----------|
| IG | ✅ | ✅ | ✅ | ✅ | ✅ |
| FB | ✅ | ✅ | ✅ | ❌ | ✅ |
| GBP | ✅ | ❌ | ❌ | ❌ | ❌ |

**כללים:**
- אם נבחר GBP → חסימת העלאת וידאו + הודעה למשתמש
- אם נבחר GBP עם EVENT/OFFER → פתיחת שדות תאריך / קופון / תנאים
- validation בצד הקליינט **לפני submit** (למנוע שגיאות מיותרות מצד ה-API)

---

## 8. Google Business Profile — פירוט טכני

### 8.1 קובץ חדש: `channels/google_business.py`

```python
class GoogleBusinessChannel(BaseChannel):
    CHANNEL_ID = "GBP"
    CHANNEL_NAME = "Google Business Profile"
    SUPPORTED_POST_TYPES = ["STANDARD", "EVENT", "OFFER"]
    SUPPORTED_MEDIA_TYPES = ["image"]  # GBP לא תומך בוידאו בפוסטים

    def publish(self, post_data: dict) -> PublishResult:
        """
        פרסום ל-Google Business Profile.
        1. העלאת תמונה ל-Cloudinary (כבר קיים)
        2. יצירת localPost דרך GBP API
        """
```

### 8.2 Google Business Profile API — קריאות

```python
# יצירת פוסט
POST https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/localPosts

# גוף הבקשה (STANDARD)
{
    "languageCode": "he",
    "summary": "טקסט הפוסט...",
    "media": [{
        "mediaFormat": "PHOTO",
        "sourceUrl": "https://res.cloudinary.com/..."
    }],
    "topicType": "STANDARD"   # או EVENT / OFFER
}
```

### 8.3 משתני סביבה חדשים

```env
# Google Business Profile
GBP_ACCOUNT_ID=accounts/123456789
GBP_LOCATION_ID=locations/987654321

# אימות — OAuth 2.0 (ברירת מחדל)
GBP_OAUTH_CLIENT_ID=...
GBP_OAUTH_CLIENT_SECRET=...
GBP_REFRESH_TOKEN=...
```

> **הערה לגבי אימות:** ברירת המחדל היא OAuth 2.0. שימוש ב-Service Account אפשרי רק לאחר POC שמוכיח שזה עובד עם החשבון העסקי הספציפי. תהליך הגישה ל-GBP API דורש אישור פרויקט מ-Google — פרויקט שלא אושר עלול להיות מוגבל ל-0 QPM.

---

## 9. Retry Policy

### 9.1 עקרון: retry פר ערוץ, לא לכל הפוסט

אם פוסט הצליח ב-IG ו-FB אבל נכשל ב-GBP — ננסה שוב רק את GBP.

### 9.2 סיווג שגיאות

| סוג שגיאה | Retryable? | דוגמאות |
|-----------|------------|---------|
| שגיאת רשת / timeout | ✅ כן | `ConnectionError`, `Timeout`, `502/503/504` |
| rate limit | ✅ כן | `429`, `quota_exceeded` |
| שגיאת שרת | ✅ כן | `500`, `InternalServerError` |
| תוכן לא תקין | ❌ לא | `caption_too_long`, `invalid_media_format` |
| הרשאות חסרות | ❌ לא | `403`, `insufficient_permissions` |
| משאב לא נמצא | ❌ לא | `404`, `location_not_found` |

### 9.3 מדיניות retry אוטומטי

- **מספר ניסיונות:** עד 3 (כולל הניסיון הראשוני)
- **ביניהם:** exponential backoff — 30s, 120s, 300s
- **rate limit:** המתנה לפי `Retry-After` header אם קיים, אחרת 60s
- **לאחר 3 ניסיונות כושלים:** סימון `ERROR` + retry ידני בלבד מה-UI

### 9.4 גישת MVP

בשלב הראשון — **retry ידני בלבד** דרך כפתור "נסה שוב" בפאנל.
retry אוטומטי ייכנס רק לאחר שהמערכת יציבה.

---

## 10. Observability

### 10.1 לוגים מובנים

כל ניסיון פרסום ירשום:

| שדה | תיאור | דוגמה |
|------|--------|--------|
| `correlation_id` | מזהה ייחודי ל-job (כל הערוצים של אותו פוסט) | `job_20260327_180005_abc` |
| `channel` | ערוץ ספציפי | `GBP` |
| `action` | מה נעשה | `publish`, `validate`, `retry` |
| `started_at` | זמן התחלה | `2026-03-27T18:00:05Z` |
| `ended_at` | זמן סיום | `2026-03-27T18:00:07Z` |
| `status` | תוצאה | `success`, `error` |
| `error_raw` | הודעת שגיאה גולמית מה-API | `{"error": {"code": 429, ...}}` |
| `error_friendly` | הודעה ידידותית ל-UI | `חריגה ממכסת בקשות — נסה שוב מאוחר יותר` |

### 10.2 התראות Telegram

הרחבת מערכת ההתראות הקיימת:
- שגיאה בערוץ ספציפי (עם `correlation_id`)
- סטטוס `PARTIAL` — הצלחה חלקית
- timeout על שורה `PROCESSING`

---

## 11. שלבי פיתוח

### שלב 1: Channel Layer (ארכיטקטורה)
- [ ] יצירת תיקיית `channels/` עם `base.py` ו-`registry.py`
- [ ] מיגרציה של IG/FB הקיימים לתוך ה-Channel Interface (עטיפה, לא שכתוב)
- [ ] עדכון `main.py` לעבוד דרך Registry
- [ ] טסטים — ווידוא שהזרימה הקיימת עובדת כמו קודם

### שלב 2: Google Business Profile (STANDARD בלבד)
- [ ] POC אימות — OAuth 2.0 מול חשבון GBP אמיתי
- [ ] אימות מכסות API בפועל מול הפרויקט
- [ ] מימוש `GoogleBusinessChannel` — סוג `STANDARD` בלבד
- [ ] טסטים
- [ ] **שלב 2b (לאחר יציבות):** הוספת EVENT ו-OFFER עם שדות תאריך/קופון

### שלב 3: עדכון UI
- [ ] בחירת ערוצים מרובים בטופס יצירת פוסט
- [ ] שדה caption נפרד לכל ערוץ
- [ ] תצוגת סטטוס מרובה ערוצים
- [ ] פילטר לפי ערוץ
- [ ] כפתור "נסה שוב" לערוץ ספציפי שנכשל

### שלב 4: עדכון Google Sheets
- [ ] הוספת עמודות חדשות (כולל `locked_at`, `run_id`, `retry_count`)
- [ ] מימוש מנגנון PROCESSING / lock למניעת פרסום כפול
- [ ] עדכון לוגיקת סטטוס (PARTIAL)
- [ ] עדכון `result_detail` לפורמט מרובה ערוצים

### שלב 5: חיבור למערכת AI
- [ ] יישום Data Contract (סעיף 6.2) מול מערכת ה-AI
- [ ] ולידציה של שורות נכנסות לפי חוזה הנתונים
- [ ] מימוש לוגיקת fallback לכיתובים
- [ ] ווידוא קליטה אוטומטית
- [ ] טסטים E2E

---

## 12. סיכום טכני

| נושא | פרטים |
|------|--------|
| **שפה** | Python 3.12 |
| **Framework** | Flask |
| **DB** | Google Sheets (ללא שינוי) |
| **מדיה** | Google Drive → Cloudinary (ללא שינוי) |
| **APIs חדשים** | Google Business Profile API |
| **APIs קיימים** | Meta Graph API (IG + FB) — ללא שינוי |
| **דיפלוי** | Render (ללא שינוי) |
| **ערוצים בשלב 1** | IG, FB, GBP |
| **ערוצים עתידיים אפשריים** | LinkedIn, Twitter/X, TikTok, Pinterest |

### עיקרון מנחה
> **הוספת ערוץ חדש = קובץ Python חדש בתיקיית `channels/` + רישום ב-Registry.**
> אין צורך לשנות את `main.py`, את ה-UI, או את מבנה הטבלה (מעבר להוספת עמודת caption).

---

## 13. שאלות פתוחות לבירור עם הלקוח

1. **אימות GBP:** יש לבצע POC עם OAuth 2.0 מול החשבון העסקי. האם יש גישה פעילה ל-GBP API?
2. **אישור פרויקט Google:** האם הפרויקט ב-Google Cloud אושר לשימוש ב-Business Profile API? (ללא אישור — 0 QPM)
3. **סוג פוסט GBP:** נתחיל עם STANDARD בלבד. האם EVENT ו-OFFER נדרשים לגרסה הראשונה?
4. **תמונות GBP:** האם כל פוסט ב-GBP חייב תמונה, או שאפשר גם טקסט בלבד?
5. **מספר Locations:** האם הלקוח מנהל מיקום אחד או כמה (multi-location)?
6. **פורמט ה-Sheets:** האם מערכת ה-AI יכולה לעבוד לפי Data Contract (סעיף 6.2) — כולל `caption_gbp`, `gbp_post_type`, `source`?
7. **Retry:** ב-MVP נתחיל עם retry ידני בלבד. האם יש צורך דחוף ב-retry אוטומטי?
8. **התראות:** האם להרחיב את התראות הטלגרם גם ל-GBP?
9. **Timezone:** האם `scheduled_time` צריך להיות תמיד Asia/Jerusalem, או שנדרש timezone דינמי?
