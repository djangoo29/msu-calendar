import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import uuid
from flask import Flask, request, Response, render_template_string
import os

app = Flask(__name__)

BASE_URL = "http://timetable.msu.az"

HARD_CODED_USER = os.environ.get("MSU_USER", "msu")
HARD_CODED_PASS = os.environ.get("MSU_PASS", "msu2013")

FACULTIES = {
    "22": "Филология - Русское отделение М.",
    "3": "Филология - Русское отделение",
    "5": "Филология - Французское отделение",
    "26": "Филология - Французское отделение М.",
    "6": "Филология - Английское отделение",
    "23": "Филология - Английское отделение М.",
    "7": "Филология - Итальянское отделение",
    "24": "Филология - Итальянское отделение М.",
    "4": "Филология - Испанское отделение",
    "25": "Филология - Испанское отделение М.",
    "11": "Химия",
    "17": "Химия - Физическая химия М.",
    "14": "Химия - Физхимия",
    "12": "Химия - Нефтехимия",
    "19": "Химия - Нефтехимия М.",
    "13": "Химия - Органика",
    "18": "Химия - Органическая химия М.",
    "27": "Химия М.",
    "10": "Математика и компьютерные науки",
    "28": "Математика и компьютерные науки М.",
    "1": "Менеджмент",
    "2": "Экономика",
    "16": "Спец практикум-1",
    "8": "Психология",
    "21": "Психология М.",
    "9": "Прикладная математика",
    "20": "Прикладная математика М.",
}

COURSES = {"1": "1 курс", "2": "2 курс", "3": "3 курс", "4": "4 курс"}

DAYS_RU = {
    "понедельник": 0, "вторник": 1, "среда": 2,
    "четверг": 3, "пятница": 4, "суббота": 5,
}


def get_current_week_monday():
    today = datetime.now()
    return today - timedelta(days=today.weekday())


def escape_ics(text):
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


class TimetableParser:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()

    def login(self):
        self.session.get(BASE_URL)
        r = self.session.post(
            f"{BASE_URL}/index.php",
            data={"username": self.username, "password": self.password, "submit": "Войти"},
        )
        return "password" not in r.text.lower() or "main.php" in r.text.lower()

    def get_schedule(self, faculty, course):
        r = self.session.post(f"{BASE_URL}/process.php", data={"pagenum": "tdeduGraph_common"})
        soup = BeautifulSoup(r.text, "html.parser")

        form_action = None
        form = soup.find("form")
        if form and form.get("action"):
            form_action = form["action"]

        data = {"repProfId": faculty, "repCourseId": course}

        week_select = soup.find("select", {"id": "repWeekId"})
        if week_select:
            selected = week_select.find("option", {"selected": True})
            if selected and selected.get("value"):
                data["repWeekId"] = selected["value"]
            else:
                for opt in week_select.find_all("option"):
                    if opt.get("value") and opt["value"] != "0":
                        data["repWeekId"] = opt["value"]
                        break

        if "repWeekId" not in data:
            data["repWeekId"] = "0"

        data["repGraph"] = "Расписание"
        url = f"{BASE_URL}/{form_action}" if form_action else f"{BASE_URL}/process.php"
        r2 = self.session.post(url, data=data)
        return self._parse(r2.text)

    def _parse(self, html):
        soup = BeautifulSoup(html, "html.parser")
        schedule = []

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 3:
                    texts = [c.get_text(strip=True) for c in cells]
                    row_text = " ".join(texts).lower()

                    for day_name in DAYS_RU:
                        if day_name in row_text:
                            info = self._extract(cells)
                            if info:
                                info["day"] = day_name
                                schedule.append(info)
                            break

        if not schedule:
            schedule = self._parse_text(soup)

        return schedule

    def _extract(self, cells):
        texts = [c.get_text(strip=True) for c in cells]
        info = {}

        for text in texts:
            m = re.search(r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})", text)
            if m:
                info["time_start"] = m.group(1).replace(".", ":")
                info["time_end"] = m.group(2).replace(".", ":")
                continue
            if re.match(r"\d{1,2}[:.]\d{2}$", text):
                key = "time_start" if "time_start" not in info else "time_end"
                info[key] = text.replace(".", ":")
                continue
            if any(k in text.lower() for k in ["аудитория", "ауд", "кабинет", "каб"]):
                info["room"] = text
                continue
            if "subject" not in info and len(text) > 2 and not re.match(r"^\d+$", text):
                info["subject"] = text

        return info if "time_start" in info and "time_end" in info else None

    def _parse_text(self, soup):
        schedule = []
        current_day = None
        for line in soup.get_text().split("\n"):
            line = line.strip()
            if not line:
                continue
            for d in DAYS_RU:
                if d in line.lower():
                    current_day = d
                    break
            if current_day:
                m = re.search(r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})", line)
                if m:
                    parts = line.split(m.group(0))
                    schedule.append({
                        "day": current_day,
                        "time_start": m.group(1).replace(".", ":"),
                        "time_end": m.group(2).replace(".", ":"),
                        "subject": parts[0].strip() if parts else "",
                        "room": "",
                    })
        return schedule


def generate_ics(schedule, faculty_name="", course_name=""):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    monday = get_current_week_monday()

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//MSU Timetable//Cloud//RU",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:Расписание МГУ - {faculty_name} {course_name}",
        "X-WR-TIMEZONE:Asia/Baku",
    ]

    for lesson in schedule:
        day_num = DAYS_RU.get(lesson.get("day", ""))
        if day_num is None:
            continue

        event_date = monday + timedelta(days=day_num)

        try:
            h, m = map(int, lesson.get("time_start", "09:00").split(":"))
            start_dt = event_date.replace(hour=h, minute=m, second=0, microsecond=0)
        except (ValueError, AttributeError):
            start_dt = event_date.replace(hour=9, minute=0, second=0, microsecond=0)

        try:
            h, m = map(int, lesson.get("time_end", "10:30").split(":"))
            end_dt = event_date.replace(hour=h, minute=m, second=0, microsecond=0)
        except (ValueError, AttributeError):
            end_dt = start_dt + timedelta(hours=1, minutes=30)

        subject = lesson.get("subject", "Пара")
        room = lesson.get("room", "")
        uid = str(uuid.uuid4())

        desc = f"Аудитория: {room}\\nДень: {lesson.get('day', '').title()}" if room else f"День: {lesson.get('day', '').title()}"

        lines.extend([
            "BEGIN:VEVENT",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            "RRULE:FREQ=WEEKLY",
            f"UID:{uid}", f"DTSTAMP:{now}",
            f"SUMMARY:{escape_ics(subject)}",
            f"DESCRIPTION:{escape_ics(desc)}",
        ])

        if room:
            lines.append(f"LOCATION:{escape_ics(room)}")

        lines.extend([
            "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY",
            "DESCRIPTION:Пара через 15 минут", "END:VALARM", "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


PAGE_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Расписание МГУ Баку</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f0c29;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.box{max-width:600px;width:100%}
h1{font-size:22px;margin-bottom:6px;color:#fff}
.sub{color:#9a9abf;font-size:13px;margin-bottom:24px}
label{display:block;font-size:13px;color:#b0b0d0;margin-bottom:5px;margin-top:14px}
select{width:100%;padding:12px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:10px;color:#fff;font-size:14px;appearance:none;outline:none}
select option{background:#1a1a3e;color:#fff}
button{width:100%;margin-top:18px;padding:14px;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
button:hover{opacity:.9}
.result{margin-top:20px;padding:18px;background:rgba(255,255,255,.05);border-radius:12px;border:1px solid rgba(255,255,255,.1);display:none}
.result h3{font-size:14px;color:#667eea;margin-bottom:10px}
.url-box{background:rgba(0,0,0,.3);padding:12px;border-radius:8px;word-break:break-all;font-family:monospace;font-size:12px;color:#38ef7d;margin-bottom:10px}
.copy-btn{padding:8px 16px;border:1px solid rgba(255,255,255,.2);border-radius:8px;background:transparent;color:#e0e0e0;font-size:13px;cursor:pointer;margin-top:6px}
.copy-btn:hover{background:rgba(255,255,255,.1)}
.help{margin-top:16px;font-size:13px;color:#9a9abf;line-height:1.7}
.help b{color:#e0e0e0}
</style>
</head>
<body>
<div class="box">
<h1>Расписание МГУ Баку</h1>
<p class="sub">Филиал МГУ им. М.В. Ломоносова в Баку</p>

<label>Факультет</label>
<select id="fac">
<option value="">-- Выберите --</option>
{% for id, name in faculties.items() %}
<option value="{{id}}">{{name}}</option>
{% endfor %}
</select>

<label>Курс</label>
<select id="crs">
<option value="">-- Выберите --</option>
{% for id, name in courses.items() %}
<option value="{{id}}">{{name}}</option>
{% endfor %}
</select>

<button onclick="gen()">Получить ссылку</button>

<div class="result" id="res">
<h3>Ссылка для календаря:</h3>
<div class="url-box" id="url"></div>
<button class="copy-btn" onclick="copy()">Копировать ссылку</button>
<div class="help">
<b>Apple Calendar:</b><br>
1. Скопируйте ссылку<br>
2. На iPhone: Настройки → Почта → Учётные записи → Добавить учётную запись → Другое<br>
3. Вставьте ссылку в поле «URL»<br><br>
<b>Google Calendar:</b><br>
1. Откройте calendar.google.com<br>
2. Слева нажмите «+» → «СbindParam из URL»<br>
3. Вставьте ссылку<br><br>
Расписание обновляется <b>автоматически</b> каждую неделю.
</div>
</div>
</div>
<script>
function gen(){
var f=document.getElementById('fac').value,c=document.getElementById('crs').value;
if(!f||!c){alert('Выберите факультет и курс');return}
var u=location.origin+'/ics/'+f+'/'+c+'.ics';
document.getElementById('url').textContent=u;
document.getElementById('res').style.display='block';
}
function copy(){
navigator.clipboard.writeText(document.getElementById('url').textContent);
alert('Скопировано!');
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE_HTML, faculties=FACULTIES, courses=COURSES)


@app.route("/ics/<faculty>/<course>.ics")
def ics_feed(faculty, course):
    parser = TimetableParser(HARD_CODED_USER, HARD_CODED_PASS)
    if not parser.login():
        return Response("Authentication failed", status=401)

    schedule = parser.get_schedule(faculty, course)
    if not schedule:
        return Response("Schedule not found", status=404)

    faculty_name = FACULTIES.get(faculty, faculty)
    course_name = COURSES.get(course, course)
    ics_content = generate_ics(schedule, faculty_name, course_name)

    return Response(
        ics_content,
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="msu_{faculty}_{course}.ics"'},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
