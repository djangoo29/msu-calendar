import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageDraw, ImageFont
import os


BASE_URL = "http://timetable.msu.az"

# Захардкоженные данные для входа
HARD_CODED_USER = "msu"
HARD_CODED_PASS = "msu2013"

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
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
}

DAYS_ORDER = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]

SLOT_TIMES = {
    "I": ("09:00", "10:20"),
    "II": ("10:30", "11:50"),
    "III": ("12:00", "13:20"),
    "IV": ("14:00", "15:20"),
    "V": ("15:30", "16:50"),
    "VI": ("17:00", "18:20"),
}


class TimetableParser:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
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
        self.session.get(f"{BASE_URL}/main.php")
        self.logged_in = r.url.endswith("main.php") or "main.php" in r.text.lower()
        return self.logged_in

    def get_schedule(self, faculty, course):
        r = self.session.post(
            f"{BASE_URL}/pages.php",
            data={"pagenum": "tdedu_graph_common"},
            headers=self.headers,
        )
        form_path = r.text.strip()
        if not form_path:
            return []

        r2 = self.session.get(f"{BASE_URL}/{form_path}", headers=self.headers)
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
        soup3 = BeautifulSoup(r3.text, "html.parser")
        week_select = soup3.find("select", {"id": "repWeekId"})

        week_ids = []
        if week_select:
            for o in week_select.find_all("option"):
                if o.get("value") and o["value"] != "0":
                    week_ids.append((o["value"], o.text.strip()))

        if not week_ids:
            return []

        schedule = []
        for wid, wlabel in week_ids:
            r4 = self.session.post(
                f"{BASE_URL}/process.php",
                data={"profid": faculty, "courseid": course, "weekid": wid, "inf": inf},
                headers=self.headers,
            )
            schedule.extend(self._parse_tbl_report(r4.text))

        return schedule

    def _parse_tbl_report(self, html):
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "tblReport"})
        if not table:
            return []

        schedule = []
        rows = table.find_all("tr")

        current_date = None
        current_day_name = None
        consumed_rows = 0

        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            texts = [c.get_text(strip=True) for c in cells]

            if consumed_rows > 0:
                consumed_rows -= 1
                slot_text = texts[0].strip().upper().replace(".", "") if texts else ""
                if slot_text in SLOT_TIMES:
                    time_text = texts[1] if len(texts) > 1 else ""
                    t_start, t_end = self._parse_time_range(time_text)
                    subject = texts[3] if len(texts) > 3 else ""
                    room = texts[2] if len(texts) > 2 else ""
                    teacher = texts[4] if len(texts) > 4 else ""
                    if subject.strip():
                        schedule.append({
                            "day": current_day_name, "date": current_date,
                            "time_start": t_start, "time_end": t_end,
                            "subject": subject.strip(), "room": room.strip(),
                            "teacher": teacher.strip(),
                        })
                continue

            first_cell = cells[0]
            rowspan = first_cell.get("rowspan")
            if rowspan:
                try:
                    consumed_rows = int(rowspan) - 1
                except ValueError:
                    consumed_rows = 0

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

                slot_text = texts[2].strip().upper().replace(".", "") if len(texts) > 2 else ""
                if slot_text in SLOT_TIMES:
                    time_text = texts[3] if len(texts) > 3 else ""
                    t_start, t_end = self._parse_time_range(time_text)
                    subject = texts[5] if len(texts) > 5 else ""
                    room = texts[4] if len(texts) > 4 else ""
                    teacher = texts[6] if len(texts) > 6 else ""
                    if subject.strip():
                        schedule.append({
                            "day": current_day_name, "date": current_date,
                            "time_start": t_start, "time_end": t_end,
                            "subject": subject.strip(), "room": room.strip(),
                            "teacher": teacher.strip(),
                        })

        return schedule

    def _parse_time_range(self, text):
        m = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", text)
        if m:
            return m.group(1), m.group(2)
        return "09:00", "10:30"
                    subject = parts[0].strip() if parts else ""
                    schedule.append({
                        "day": current_day,
                        "time_start": time_match.group(1).replace(".", ":"),
                        "time_end": time_match.group(2).replace(".", ":"),
                        "subject": subject,
                        "room": "",
                    })

        return schedule


def get_current_week_monday():
    today = datetime.now()
    return today - timedelta(days=today.weekday())


def escape_ics(text):
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generate_ics(schedule, faculty_name="", course_name=""):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    monday = get_current_week_monday()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MSU Timetable//Parser//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Расписание МГУ - {faculty_name} {course_name}",
        "X-WR-TIMEZONE:Asia/Baku",
    ]

    for lesson in schedule:
        day_name = lesson.get("day", "")
        day_num = DAYS_RU.get(day_name)
        if day_num is None:
            continue

        event_date = monday + timedelta(days=day_num)

        time_start = lesson.get("time_start", "09:00")
        time_end = lesson.get("time_end", "10:30")

        try:
            h, m = map(int, time_start.split(":"))
            start_dt = event_date.replace(hour=h, minute=m, second=0, microsecond=0)
        except (ValueError, AttributeError):
            start_dt = event_date.replace(hour=9, minute=0, second=0, microsecond=0)

        try:
            h, m = map(int, time_end.split(":"))
            end_dt = event_date.replace(hour=h, minute=m, second=0, microsecond=0)
        except (ValueError, AttributeError):
            end_dt = start_dt + timedelta(hours=1, minutes=30)

        subject = lesson.get("subject", "Пара")
        room = lesson.get("room", "")

        description_parts = []
        if room:
            description_parts.append(f"Аудитория: {room}")
        description_parts.append(f"День: {day_name.title()}")
        description = "\\n".join(description_parts)

        uid = str(uuid.uuid4())

        lines.extend([
            "BEGIN:VEVENT",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"RRULE:FREQ=WEEKLY",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"SUMMARY:{escape_ics(subject)}",
            f"DESCRIPTION:{escape_ics(description)}",
        ])

        if room:
            lines.append(f"LOCATION:{escape_ics(room)}")

        lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            "DESCRIPTION:Пара через 15 минут",
            "END:VALARM",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def generate_schedule_image(schedule, faculty_name="", course_name=""):
    width = 900
    padding = 30
    line_height = 36
    day_header_height = 44
    title_height = 70

    days_data = {d: [] for d in DAYS_ORDER}
    for lesson in schedule:
        day = lesson.get("day", "")
        if day in days_data:
            days_data[day].append(lesson)

    total_height = title_height + padding
    for day in DAYS_ORDER:
        lessons = days_data[day]
        if lessons:
            total_height += day_header_height + len(lessons) * line_height + 20

    total_height = max(total_height, 400)

    img = Image.new("RGB", (width, total_height), "#1a1a2e")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 22)
        font_subtitle = ImageFont.truetype("arial.ttf", 14)
        font_day = ImageFont.truetype("arial.ttf", 16)
        font_text = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        try:
            font_title = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
            font_subtitle = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
            font_day = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
            font_text = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
        except OSError:
            font_title = ImageFont.load_default()
            font_subtitle = font_title
            font_day = font_title
            font_text = font_title

    y = padding
    draw.text((padding, y), "Расписание занятий", fill="#e0e0ff", font=font_title)
    y += 30
    draw.text((padding, y), f"{faculty_name} | {course_name}", fill="#8888aa", font=font_subtitle)
    y += 30

    monday = get_current_week_monday()
    week_str = f"Неделя: {monday.strftime('%d.%m')} - {(monday + timedelta(days=6)).strftime('%d.%m.%Y')}"
    draw.text((padding, y), week_str, fill="#6666aa", font=font_subtitle)
    y += 30

    draw.line([(padding, y), (width - padding, y)], fill="#333366", width=1)
    y += 15

    day_names_pretty = {
        "понедельник": "Понедельник",
        "вторник": "Вторник",
        "среда": "Среда",
        "четверг": "Четверг",
        "пятница": "Пятница",
        "суббота": "Суббота",
    }

    for day in DAYS_ORDER:
        lessons = days_data[day]
        if not lessons:
            continue

        lessons.sort(key=lambda x: x.get("time_start", ""))

        draw.rounded_rectangle(
            [(padding, y), (width - padding, y + day_header_height - 4)],
            radius=8,
            fill="#16213e",
        )
        draw.text(
            (padding + 15, y + 10),
            day_names_pretty.get(day, day.title()),
            fill="#667eea",
            font=font_day,
        )
        y += day_header_height

        for i, lesson in enumerate(lessons):
            bg = "#1a1a2e" if i % 2 == 0 else "#1e1e3a"
            draw.rounded_rectangle(
                [(padding + 10, y), (width - padding - 10, y + line_height - 4)],
                radius=6,
                fill=bg,
            )

            time_str = f"{lesson.get('time_start', '?')} - {lesson.get('time_end', '?')}"
            draw.text((padding + 20, y + 6), time_str, fill="#9a9abf", font=font_text)

            subject = lesson.get("subject", "Пара")
            draw.text((padding + 160, y + 6), subject, fill="#e0e0e0", font=font_text)

            room = lesson.get("room", "")
            if room:
                draw.text((width - padding - 150, y + 6), room, fill="#667eea", font=font_text)

            y += line_height

        y += 10

    return img


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Расписание МГУ Баку")
        self.root.geometry("700x800")
        self.root.configure(bg="#0f0c29")
        self.root.resizable(True, True)

        self.parser = None
        self.schedule = []

        self.build_ui()
        self.center_window()
        self.auto_login()

    def center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background="#0f0c29")
        style.configure("TLabel", background="#0f0c29", foreground="#e0e0e0", font=("Segoe UI", 11))
        style.configure("Title.TLabel", background="#0f0c29", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#0f0c29", foreground="#9a9abf", font=("Segoe UI", 10))
        style.configure("Step.TLabel", background="#0f0c29", foreground="#667eea", font=("Segoe UI", 12, "bold"))

        style.configure("TButton", font=("Segoe UI", 11), padding=10)
        style.configure("Primary.TButton", background="#667eea", foreground="white")
        style.configure("Success.TButton", background="#38ef7d", foreground="#1a1a2e")
        style.configure("Calendar.TButton", background="#16213e", foreground="#e0e0e0")

        style.configure("TCombobox", font=("Segoe UI", 11), padding=8)
        style.configure("TEntry", font=("Segoe UI", 11), padding=8)

        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Расписание занятий", style="Title.TLabel").pack(pady=(0, 5))
        ttk.Label(main, text="Филиал МГУ им. М.В. Ломоносова в Баку", style="Subtitle.TLabel").pack(pady=(0, 20))

        # --- STATUS ---
        self.status_frame = ttk.Frame(main)
        self.status_frame.pack(fill=tk.X, pady=(0, 10))
        self.status_label = ttk.Label(self.status_frame, text="Подключение к серверу...", foreground="#9a9abf")
        self.status_label.pack(anchor=tk.W)

        # --- SELECT ---
        select_frame = ttk.LabelFrame(main, text="  Выбор расписания  ", padding=15)
        select_frame.pack(fill=tk.X, pady=(0, 10))
        self.select_frame = select_frame
        self.select_frame.pack_forget()

        row = ttk.Frame(select_frame)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="Факультет:", width=12).pack(side=tk.LEFT)
        self.faculty_var = tk.StringVar()
        faculty_names = {v: v for v in FACULTIES.values()}
        self.faculty_cb = ttk.Combobox(
            row, textvariable=self.faculty_var, values=list(faculty_names.keys()), state="readonly", width=45
        )
        self.faculty_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row2 = ttk.Frame(select_frame)
        row2.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row2, text="Курс:", width=12).pack(side=tk.LEFT)
        self.course_var = tk.StringVar()
        self.course_cb = ttk.Combobox(
            row2, textvariable=self.course_var, values=list(COURSES.values()), state="readonly", width=20
        )
        self.course_cb.pack(side=tk.LEFT)

        self.fetch_btn = ttk.Button(select_frame, text="Получить расписание", command=self.do_fetch, style="Primary.TButton")
        self.fetch_btn.pack(fill=tk.X, pady=(5, 0))

        self.fetch_status = ttk.Label(select_frame, text="", foreground="#ff6b6b")
        self.fetch_status.pack(anchor=tk.W)

        # --- RESULT ---
        result_frame = ttk.LabelFrame(main, text="  Расписание  ", padding=15)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.result_frame = result_frame
        self.result_frame.pack_forget()

        text_frame = ttk.Frame(result_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.schedule_text = tk.Text(
            text_frame, bg="#1a1a2e", fg="#e0e0e0", insertbackground="#667eea",
            font=("Consolas", 11), wrap=tk.WORD, yscrollcommand=scrollbar.set,
            relief=tk.FLAT, padx=10, pady=10
        )
        self.schedule_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.schedule_text.yview)

        self.schedule_text.tag_configure("day", foreground="#667eea", font=("Consolas", 12, "bold"))
        self.schedule_text.tag_configure("time", foreground="#9a9abf")
        self.schedule_text.tag_configure("subject", foreground="#e0e0e0")
        self.schedule_text.tag_configure("room", foreground="#667eea")

        btn_frame = ttk.Frame(result_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Скачать ICS", command=self.download_ics, style="Success.TButton").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Сохранить изображение", command=self.download_image, style="Success.TButton").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Ссылка Apple Calendar", command=self.show_apple_link, style="Calendar.TButton").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Ссылка Google Calendar", command=self.show_google_link, style="Calendar.TButton").pack(side=tk.LEFT)

        self.links_frame = ttk.Frame(result_frame)
        self.links_frame.pack(fill=tk.X, pady=(10, 0))

    def auto_login(self):
        self.parser = TimetableParser(HARD_CODED_USER, HARD_CODED_PASS)
        self.root.update()

        if self.parser.login():
            self.status_label.config(text="Готово к работе", foreground="#38ef7d")
            self.select_frame.pack(fill=tk.X, pady=(0, 10))
        else:
            self.status_label.config(text="Ошибка входа. Проверьте данные в коде.", foreground="#ff6b6b")

    def do_fetch(self):
        faculty_name = self.faculty_var.get()
        course_name = self.course_var.get()

        if not faculty_name or not course_name:
            self.fetch_status.config(text="Выберите факультет и курс")
            return

        faculty_id = None
        for k, v in FACULTIES.items():
            if v == faculty_name:
                faculty_id = k
                break

        course_id = None
        for k, v in COURSES.items():
            if v == course_name:
                course_id = k
                break

        if not faculty_id or not course_id:
            self.fetch_status.config(text="Ошибка выбора")
            return

        self.fetch_status.config(text="Загрузка...")
        self.root.update()

        self.schedule = self.parser.get_schedule(faculty_id, course_id)

        if not self.schedule:
            self.fetch_status.config(text="Расписание не найдено. Попробуйте другой факультет/курс.", foreground="#ff6b6b")
            return

        self.fetch_status.config(text=f"Найдено пар: {len(self.schedule)}", foreground="#38ef7d")

        self.select_frame.pack_forget()
        self.result_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.show_schedule_text(faculty_name, course_name)

    def show_schedule_text(self, faculty_name, course_name):
        self.schedule_text.config(state=tk.NORMAL)
        self.schedule_text.delete("1.0", tk.END)

        self.schedule_text.insert(tk.END, f"{faculty_name}\n", "day")
        self.schedule_text.insert(tk.END, f"{course_name}\n\n", "time")

        days_data = {d: [] for d in DAYS_ORDER}
        for lesson in self.schedule:
            day = lesson.get("day", "")
            if day in days_data:
                days_data[day].append(lesson)

        for day in DAYS_ORDER:
            lessons = days_data[day]
            if not lessons:
                continue

            lessons.sort(key=lambda x: x.get("time_start", ""))

            self.schedule_text.insert(tk.END, f"━━ {day.title()} ━━\n", "day")

            for lesson in lessons:
                time_str = f"  {lesson.get('time_start', '?'):5} - {lesson.get('time_end', '?'):5}  "
                self.schedule_text.insert(tk.END, time_str, "time")

                subject = lesson.get("subject", "Пара")
                self.schedule_text.insert(tk.END, subject, "subject")

                room = lesson.get("room", "")
                if room:
                    self.schedule_text.insert(tk.END, f"  [{room}]", "room")

                self.schedule_text.insert(tk.END, "\n")

            self.schedule_text.insert(tk.END, "\n")

        self.schedule_text.config(state=tk.NORMAL)

    def download_ics(self):
        if not self.schedule:
            return

        faculty_name = self.faculty_var.get()
        course_name = self.course_var.get()

        ics_content = generate_ics(self.schedule, faculty_name, course_name)

        filename = filedialog.asksaveasfilename(
            defaultextension=".ics",
            filetypes=[("ICS files", "*.ics")],
            initialfile=f"msu_{faculty_name[:20]}_{course_name}.ics",
        )

        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(ics_content)
            messagebox.showinfo("Готово", f"Файл сохранён:\n{filename}")

    def download_image(self):
        if not self.schedule:
            return

        faculty_name = self.faculty_var.get()
        course_name = self.course_var.get()

        img = generate_schedule_image(self.schedule, faculty_name, course_name)

        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG images", "*.png")],
            initialfile=f"msu_{faculty_name[:20]}_{course_name}.png",
        )

        if filename:
            img.save(filename, "PNG")
            messagebox.showinfo("Готово", f"Изображение сохранено:\n{filename}")

    def show_apple_link(self):
        self._clear_links()
        ttk.Label(
            self.links_frame,
            text="Apple Calendar: скачайте ICS файл и откройте на iPhone/Mac",
            foreground="#9a9abf", wraplength=600
        ).pack(anchor=tk.W)
        ttk.Label(
            self.links_frame,
            text="Или: Файл → Присоединиться к календарю → выберите ICS файл",
            foreground="#9a9abf", wraplength=600
        ).pack(anchor=tk.W)

    def show_google_link(self):
        self._clear_links()
        ttk.Label(
            self.links_frame,
            text="Google Calendar:",
            foreground="#9a9abf"
        ).pack(anchor=tk.W)
        steps = [
            "1. Скачайте ICS файл",
            "2. Откройте calendar.google.com",
            "3. Настройки → Импорт и экспорт → Импорт",
            "4. Загрузите скачанный ICS файл",
        ]
        for step in steps:
            ttk.Label(self.links_frame, text=f"   {step}", foreground="#9a9abf").pack(anchor=tk.W)

    def _clear_links(self):
        for widget in self.links_frame.winfo_children():
            widget.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = App()
    app.run()
