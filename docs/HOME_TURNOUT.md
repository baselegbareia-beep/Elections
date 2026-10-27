# איסוף אחוזי ההצבעה מהמחשב בבית (27.10.2026)

מפת ההצבעה של ועדת הבחירות (https://mapvotes.bechirot.gov.il) נפתחת רק ממחשב בישראל, ולכן השרתים של GitHub לא יכולים לקרוא ממנה את אחוזי ההצבעה לפי קלפי. הסקריפט `tools/home_turnout.py` רץ על המחשב שלכם עד 22:15: כל 10 דקות הוא פותח את המפה, בדיוק כמו הדפדפן שלכם, שומר את מה שהמפה טוענת ומעלה את זה לענף `home-capture` במאגר. הוא נעצר לבד ב-22:15.

## 1. להתקין Python (פעם אחת)

- **Windows:** להיכנס ל-https://www.python.org/downloads/windows ← תחת **Stable Releases**, בגרסה הראשונה ברשימה: **Download Windows installer (64-bit)**. להריץ את הקובץ. **בחלון הראשון של ההתקנה לסמן ✔ ‏Add python.exe to PATH**, ואז Install Now.
  - אם הורד במקום זה **Python install manager** (אין בו את התיבה הזו): להתקין אותו כרגיל. בהפעלה הראשונה הוא שואל שאלות בחלון השחור: לענות `y` ו-Enter על כולן ולחכות שיסיים.
- **Mac:** להיכנס ל-https://www.python.org/downloads, להוריד את ה-macOS installer ולהתקין (Continue / Install עד הסוף).

בדיקה: ב-Windows לפתוח PowerShell **חדש** (אחרי ההתקנה) ולכתוב `py --version`; ב-Mac לפתוח Terminal ולכתוב `python3 --version`. צריך לראות 3.9 ומעלה.

## 2. ליצור טוקן של GitHub (פעם אחת, כ-2 דקות)

ב-GitHub: תמונת הפרופיל (למעלה מימין) ← **Settings** ← בתחתית התפריט: **Developer settings** ← **Personal access tokens** ← **Fine-grained tokens** ← **Generate new token**.

- **Token name:** ‏home-capture
- **Resource owner:** ‏baselegbareia-beep
- **Expiration:** ‏Custom, ותאריך של מחר (28.10), כלומר יום אחד
- **Repository access:** ‏**Only select repositories** ← לבחור **Elections** בלבד
- **Permissions:** ‏Repository permissions ← **Contents** ← **Read and write** (את Metadata ‏GitHub מוסיף לבד)
- ‏**Generate token**, ולהעתיק את הטוקן (מתחיל ב-`github_pat_`). לא לשמור אותו בקובץ ולא לשלוח אותו לאף אחד.

## 3. הפקודה האחת: הורדה והפעלה

**Windows:** תפריט התחל ← לכתוב PowerShell ← Enter. להדביק את השורה הזו (קליק ימני מדביק) וללחוץ Enter:

```powershell
irm https://raw.githubusercontent.com/baselegbareia-beep/Elections/main/tools/home_turnout.py -OutFile home_turnout.py; if (Get-Command py -ErrorAction SilentlyContinue) { py home_turnout.py } else { python home_turnout.py }
```

השורה מפעילה את `py` (מגיע עם Python מ-python.org גם בלי PATH) ורק אם אין כזה את `python`. אם בכל זאת מופיע `Python was not found; run without arguments to install from the Microsoft Store...`, או שנפתחת חנות Microsoft Store, או `python is not recognized`: Python לא מותקן כמו שצריך. להתקין לפי שלב 1, **לפתוח חלון PowerShell חדש** ולהדביק שוב את אותה שורה.

**Mac:** ‏Cmd+רווח ← לכתוב Terminal ← Enter. להדביק את השורה הזו וללחוץ Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/baselegbareia-beep/Elections/main/tools/home_turnout.py -o home_turnout.py && caffeinate -i python3 home_turnout.py
```

(`caffeinate` מונע מה-Mac להירדם כל עוד הסקריפט רץ.)

בהפעלה הראשונה הסקריפט מתקין לבד את playwright (כדקה–שתיים, רואים את ההתקדמות). אם Google Chrome לא מותקן, הוא מוריד Chromium (כ-150MB, פעם אחת). אחר כך הוא מבקש את הטוקן: להדביק (Windows: קליק ימני או Ctrl+V; ‏Mac: ‏Cmd+V) וללחוץ Enter. **לא יופיעו תווים כשמדביקים, זה תקין.**

מה רואים כשזה עובד:

```
[11:31:02] TOKEN OK | הטוקן תקין: יש גישה למאגר baselegbareia-beep/Elections.
[11:31:02] round 1: opening the map | סבב 1: פותח את המפה...
[11:31:58] round 1: 214 answers, 12 data | סבב 1: 214 תשובות מהאתר, מתוכן 12 תשובות נתונים (JSON/CSV/XML/GeoJSON/protobuf).
[11:32:05] UPLOADED 3f9c2ab | הועלה ל-GitHub (ענף home-capture): capture/20261027-1131, 18 קבצים, 1.2MB חדשים, קומיט 3f9c2ab.
[11:32:05] next round 11:41 | הסבב הבא בעוד 10 דקות (11:41).
```

בחלון של Windows העברית מופיעה לפעמים עם האותיות בסדר הפוך, או כריבועים: זה לא תקלה. לכן כל שורה חשובה מתחילה במילים באנגלית: **`UPLOADED`** = הסבב עלה ל-GitHub; **`NOT UPLOADED`** = לא עלה הפעם, נשמר במחשב וינוסה שוב בסבב הבא; `TOKEN OK` / `TOKEN REFUSED` = הטוקן תקין / לא תקין; `NO CONNECTION` = אין חיבור ל-GitHub כרגע.

## 4. לעצור

**Ctrl+C** בחלון (גם ב-Mac: ‏Control+C), או פשוט לסגור את החלון. ב-22:15 הוא נעצר לבד. כדי להפעיל שוב: אותה פקודה (הוא ישאל שוב את הטוקן).

עד אז: המחשב דלוק, מחובר לחשמל ולאינטרנט, המכסה של הלפטופ פתוח. ב-Windows הסקריפט מונע שינה כל עוד הוא רץ.

## מה הסקריפט עושה ומה לא

**עושה:**
- פותח את המפה הציבורית של הוועדה ב-Chrome שלכם, בחלון בלתי נראה, כמו כל גולש, פעם ב-10 דקות.
- אם יש במפה לשונית או שכבה "אחוזי הצבעה", לוחץ עליה (לא על שום דבר אחר).
- רושם מה המפה טענה (כתובות, וקובצי הנתונים JSON/CSV/XML), ומעלה רק לענף **‏home-capture** במאגר Elections. עותק נשמר גם בתיקייה `home_turnout_capture` ליד הסקריפט.

**לא עושה:**
- לא מתחבר לשום חשבון, לא ממלא טפסים, לא לוחץ על כפתורי שליחה או כניסה.
- לא נוגע ב-main ולא באתר שלנו, ולא בשום ענף אחר.
- לא שומר את הטוקן ולא מציג אותו. לא קורא שום דבר אחר מהמחשב.

## אם משהו לא עובד

- **`TOKEN REFUSED` "הטוקן שגוי או שפג תוקפו"** — להעתיק את הטוקן שוב, כולו (יש 3 ניסיונות). אחרת ליצור חדש.
- **"הטוקן לא נותן גישה"** או **"לטוקן אין הרשאת כתיבה"** — ליצור טוקן חדש: Only select repositories ← Elections, ו-Contents: Read and write.
- **Windows, ההורדה נכשלת (SSL/TLS)** — להריץ במקום זאת: `curl.exe -fsSL https://raw.githubusercontent.com/baselegbareia-beep/Elections/main/tools/home_turnout.py -o home_turnout.py; if (Get-Command py -ErrorAction SilentlyContinue) { py home_turnout.py } else { python home_turnout.py }`
- **`NOT UPLOADED` "לא הועלה"** — בדרך כלל האינטרנט (או רשת Wi-Fi שמבקשת התחברות). הסקריפט ממשיך, שומר במחשב ומנסה להעלות שוב בסבב הבא.
- **Mac, ‏`CERTIFICATE_VERIFY_FAILED`** — הסקריפט מטפל בזה לבד; אם זה חוזר, להריץ את Install Certificates.command מהתיקייה Applications ‏← Python 3.x.

---

### למפעיל

הפקודות למעלה מורידות את הסקריפט מ-**main**: צריך ש-`tools/home_turnout.py` יהיה ב-main לפני שמריצים אותן (עד אז הכתובת עונה 404).

`git fetch origin home-capture`, ואז בכל `capture/<YYYYMMDD-HHMM>/`: ‏`manifest.json` (כל תשובה: `url`, `method`, `status`, `type`, `bytes`, `file`, וב-POST גם `post`; וגם `clicked`, `visible_text`, `notes`), קובצי הנתונים ב-`data/`, ‏`screenshot.jpg`, הקוד של האפליקציה ב-`code/` (כל גרסה פעם אחת, לחיפוש כתובות), ו-`extra.zip` כשבסבב יש יותר מ-60 קבצים חדשים. קובץ השתתפות לפי קלפי שנמצא: `python3 pipeline/discover.py --convert FILE` ← ‏`live_input/stations.csv` עם `sectors_time` (‏[`live_input/README.md`](../live_input/README.md), ‏[`ELECTION_DAY.md`](ELECTION_DAY.md) הכנה 6). כתובת קבועה שעונה ל-JSON/CSV אפשר לנסות גם ישירות כ-`station_turnout_url`, אבל מהרנרים של GitHub היא כנראה חסומה כמו המפה.
