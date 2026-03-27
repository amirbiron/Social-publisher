# מסמך אפיון: Multi-Channel Publisher

> **תאריך:** 27.03.2026
> **סטטוס:** טיוטה לאישור
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
- **אימות:** OAuth 2.0 או Service Account
- **מגבלות:** עד 1,500 בקשות API ליום, פוסט מוגבל ל-1,500 תווים
- **סוגי פוסטים:** UPDATE (טקסט+תמונה), EVENT (אירוע עם תאריכים), OFFER (הנחה עם קופון)

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
    SUPPORTED_POST_TYPES: list    # ["FEED", "REELS"] / ["UPDATE", "EVENT"]
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
| `gbp_post_type` | סוג פוסט ב-GBP | `UPDATE` / `EVENT` / `OFFER` |
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

```
# עמודת result_detail
IG:POSTED:17841405822953 | FB:POSTED:615273820 | GBP:ERROR:quota_exceeded

# עמודת status — לוגיקה מעודכנת
POSTED       → כל הערוצים הצליחו
PARTIAL      → חלק הצליחו, חלק נכשלו (חדש!)
ERROR        → כל הערוצים נכשלו
```

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

**דרישה:** מערכת ה-AI צריכה לכתוב בפורמט הטבלה המוסכם (כולל `caption_gbp` אם רלוונטי).

### 6.2 תרחיש: התערבות ידנית

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
│  סוג פוסט GBP: [UPDATE ▾]                   │
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

---

## 8. Google Business Profile — פירוט טכני

### 8.1 קובץ חדש: `channels/google_business.py`

```python
class GoogleBusinessChannel(BaseChannel):
    CHANNEL_ID = "GBP"
    CHANNEL_NAME = "Google Business Profile"
    SUPPORTED_POST_TYPES = ["UPDATE", "EVENT", "OFFER"]
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

# גוף הבקשה (UPDATE)
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
# אימות — דרך אותו Service Account (עם הרשאות GBP)
# או OAuth2 נפרד:
GBP_OAUTH_CLIENT_ID=...
GBP_OAUTH_CLIENT_SECRET=...
GBP_REFRESH_TOKEN=...
```

---

## 9. שלבי פיתוח

### שלב 1: Channel Layer (ארכיטקטורה)
- [ ] יצירת תיקיית `channels/` עם `base.py` ו-`registry.py`
- [ ] מיגרציה של IG/FB הקיימים לתוך ה-Channel Interface (עטיפה, לא שכתוב)
- [ ] עדכון `main.py` לעבוד דרך Registry
- [ ] טסטים — ווידוא שהזרימה הקיימת עובדת כמו קודם

### שלב 2: Google Business Profile
- [ ] מימוש `GoogleBusinessChannel`
- [ ] הגדרת אימות (Service Account / OAuth)
- [ ] תמיכה בסוגי פוסטים: UPDATE, EVENT, OFFER
- [ ] טסטים

### שלב 3: עדכון UI
- [ ] בחירת ערוצים מרובים בטופס יצירת פוסט
- [ ] שדה caption נפרד לכל ערוץ
- [ ] תצוגת סטטוס מרובה ערוצים
- [ ] פילטר לפי ערוץ
- [ ] כפתור "נסה שוב" לערוץ ספציפי שנכשל

### שלב 4: עדכון Google Sheets
- [ ] הוספת עמודות חדשות
- [ ] עדכון לוגיקת סטטוס (PARTIAL)
- [ ] עדכון `result_detail` לפורמט מרובה ערוצים

### שלב 5: חיבור למערכת AI
- [ ] הגדרת פורמט הטבלה המשותף
- [ ] ווידוא קליטה אוטומטית
- [ ] טסטים E2E

---

## 10. סיכום טכני

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

## 11. שאלות פתוחות לבירור עם הלקוח

1. **אימות GBP:** האם ל-Service Account הקיים יש הרשאות ל-Google Business Profile, או שצריך OAuth נפרד?
2. **סוג פוסט GBP:** האם צריך רק UPDATE (רגיל), או גם EVENT ו-OFFER?
3. **תמונות GBP:** האם כל פוסט ב-GBP חייב תמונה, או שאפשר גם טקסט בלבד?
4. **מספר Locations:** האם הלקוח מנהל מיקום אחד או כמה (multi-location)?
5. **פורמט ה-Sheets:** האם מערכת ה-AI יכולה להוסיף את העמודות החדשות (`caption_gbp`, `gbp_post_type`)?
6. **Retry:** האם רוצים retry אוטומטי גם ל-GBP, כמו שיש ל-Meta?
7. **התראות:** האם להרחיב את התראות הטלגרם גם ל-GBP?
