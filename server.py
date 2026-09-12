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

SLOT_TIMES = {
    "I": ("08:30", "09:50"),
    "II": ("10:00", "11:20"),
    "III": ("11:30", "12:50"),
    "IV": ("13:30", "14:50"),
    "V": ("15:00", "16:20"),
    "VI": ("16:30", "17:50"),
}


def get_current_week_monday():
    today = datetime.now()
    return today - timedelta(days=today.weekday())


def escape_ics(text):
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


class TimetableParser:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.headers = {
            "Referer": f"{BASE_URL}/main.php",
            "X-Requested-With": "XMLHttpRequest",
        }

    def login(self):
        self.session.get(BASE_URL)
        r = self.session.post(
            f"{BASE_URL}/index.php",
            data={"username": self.username, "password": self.password, "submit": "Войти"},
        )
        r.encoding = "utf-8"
        self.session.get(f"{BASE_URL}/main.php")
        return r.url.endswith("main.php") or "main.php" in r.text.lower()

    def get_schedule(self, faculty, course):
        r = self.session.post(
            f"{BASE_URL}/pages.php",
            data={"pagenum": "tdedu_graph_common"},
            headers=self.headers,
        )
        r.encoding = "utf-8"
        form_path = r.text.strip()
        if not form_path:
            return [], {}

        r2 = self.session.get(f"{BASE_URL}/{form_path}", headers=self.headers)
        r2.encoding = "utf-8"
        soup = BeautifulSoup(r2.text, "html.parser")

        btn = soup.find("input", {"id": "repGraph"})
        inf = btn.get("inf", "0") if btn else "0"

        prof_select = soup.find("select", {"id": "repProfId"})
        prof_inf = prof_select.get("inf", "0") if prof_select else "0"

        r3 = self.session.post(
            f"{BASE_URL}/process.php",
            data={"prof_id": faculty, "course_id": course, "inf": prof_inf},
            headers=self.headers,
        )
        r3.encoding = "utf-8"
        soup3 = BeautifulSoup(r3.text, "html.parser")
        week_select = soup3.find("select", {"id": "repWeekId"})
        week_id = "0"
        week_label = ""
        if week_select:
            for o in week_select.find_all("option"):
                if o.get("value") and o["value"] != "0":
                    week_id = o["value"]
                    week_label = o.text.strip()
                    break

        meta = {"week_id": week_id, "week_label": week_label}
        if week_id == "0":
            return [], meta

        r4 = self.session.post(
            f"{BASE_URL}/process.php",
            data={"profid": faculty, "courseid": course, "weekid": week_id, "inf": inf},
            headers=self.headers,
        )
        r4.encoding = "utf-8"

        schedule = self._parse_tbl_report(r4.text)
        return schedule, meta

    def _parse_tbl_report(self, html):
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "tblReport"})
        if not table:
            return []

        schedule = []
        rows = table.find_all("tr")

        current_date = None
        current_day_name = None
        current_rowspan = 0
        consumed_rows = 0

        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            texts = [c.get_text(strip=True) for c in cells]

            if consumed_rows > 0:
                consumed_rows -= 1
                slot_text = texts[0] if texts else ""
                slot_text = slot_text.strip().upper().replace(".", "")
                if slot_text in SLOT_TIMES:
                    t_start, t_end = SLOT_TIMES[slot_text]
                    subject = texts[3] if len(texts) > 3 else ""
                    room = texts[2] if len(texts) > 2 else ""
                    teacher = texts[4] if len(texts) > 4 else ""
                    if subject and subject.strip():
                        schedule.append({
                            "day": current_day_name,
                            "date": current_date,
                            "time_start": t_start,
                            "time_end": t_end,
                            "subject": subject.strip(),
                            "room": room.strip(),
                            "teacher": teacher.strip(),
                        })
                continue

            first_cell = cells[0]
            rowspan = first_cell.get("rowspan")
            if rowspan:
                try:
                    current_rowspan = int(rowspan) - 1
                except ValueError:
                    current_rowspan = 0
                consumed_rows = current_rowspan

                date_text = texts[1] if len(texts) > 1 else texts[0]
                m = re.search(r"(\d{2}\.\d{2}\.\d{4})", date_text)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), "%d.%m.%Y")
                        current_date = dt
                        current_day_name = [
                            "понедельник", "вторник", "среда",
                            "четверг", "пятница", "суббота", "воскресенье"
                        ][dt.weekday()]
                    except ValueError:
                        pass

                slot_text = texts[2] if len(texts) > 2 else ""
                slot_text = slot_text.strip().upper().replace(".", "")
                if slot_text in SLOT_TIMES:
                    t_start, t_end = SLOT_TIMES[slot_text]
                    subject = texts[5] if len(texts) > 5 else ""
                    room = texts[4] if len(texts) > 4 else ""
                    teacher = texts[6] if len(texts) > 6 else ""
                    if subject and subject.strip():
                        schedule.append({
                            "day": current_day_name,
                            "date": current_date,
                            "time_start": t_start,
                            "time_end": t_end,
                            "subject": subject.strip(),
                            "room": room.strip(),
                            "teacher": teacher.strip(),
                        })

        return schedule


def generate_ics(schedule, faculty_name="", course_name=""):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//MSU Timetable//Cloud//RU",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALSCALE:UTF-8",
        f"X-WR-CALNAME:Расписание МГУ - {faculty_name} {course_name}",
        "X-WR-TIMEZONE:Asia/Baku",
    ]

    for lesson in schedule:
        event_date = lesson.get("date")
        if not event_date:
            continue

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
        teacher = lesson.get("teacher", "")
        uid = str(uuid.uuid4())

        desc_parts = []
        if room:
            desc_parts.append(f"Аудитория: {room}")
        if teacher:
            desc_parts.append(f"Преподаватель: {teacher}")
        desc = "\n".join(desc_parts) if desc_parts else ""

        lines.extend([
            "BEGIN:VEVENT",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"UID:{uid}", f"DTSTAMP:{now}",
            f"SUMMARY:{escape_ics(subject)}",
        ])

        if desc:
            lines.append(f"DESCRIPTION:{escape_ics(desc)}")
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
.msg{margin-top:12px;padding:12px;border-radius:8px;font-size:13px}
.msg-ok{background:rgba(56,239,125,.1);border:1px solid rgba(56,239,125,.3);color:#38ef7d}
.msg-err{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
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

    schedule, meta = parser.get_schedule(faculty, course)

    faculty_name = FACULTIES.get(faculty, faculty)
    course_name = COURSES.get(course, course)
    ics_content = generate_ics(schedule, faculty_name, course_name)

    ics_bytes = ics_content.encode("utf-8")

    return Response(
        ics_bytes,
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="msu_{faculty}_{course}.ics"'},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
