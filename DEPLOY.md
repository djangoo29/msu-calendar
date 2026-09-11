# Деплой на бесплатный сервер (Render)

## Пошаговая инструкция

### 1. Создай аккаунт на GitHub
- Зайди на https://github.com
- Зарегистрируйся (если ещё нет)

### 2. Создай репозиторий
- Нажми «+» → «New repository»
- Название: `msu-calendar`
- Сделай публичным (Public)
- Нажми «Create repository»

### 3. Загрузи файлы
На странице репозитория нажми «uploading an existing file» и загрузи все файлы из папки `msu-calendar`:
- `server.py`
- `requirements.txt`

Или через Git:
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/ТВОЙ_ЮЗЕРНЕЙМ/msu-calendar.git
git push -u origin main
```

### 4. Зарегистрируйся на Render
- Зайди на https://render.com
- Нажми «Get Started for Free»
- Зарегистрируйся через GitHub

### 5. Создай сервер
- Нажми «New +» → «Web Service»
- Подключи свой GitHub репозиторий `msu-calendar`
- Настройки:
  - **Name:** msu-calendar
  - **Runtime:** Python
  - **Build Command:** `pip install -r requirements.txt`
  - **Start Command:** `python server.py`
  - **Free Tier:** выбери бесплатный план

### 6. Получи ссылку
После деплоя (2-3 минуты) получишь ссылку вида:
```
https://msu-calendar.onrender.com
```

### 7. Добавь расписание в календарь
Открой ссылку в браузере, выбери факультет и курс, скопируй ссылку.

**Apple Calendar:**
1. Настройки → Почта → Учётные записи → Другое
2. Вставь ссылку в поле URL

**Google Calendar:**
1. calendar.google.com → «+» слева → «СbindParam из URL»
2. Вставь ссылку

---

## Важно
- Бесплатный план Render «засыпает» через 15 минут бездействия, потом просыпается за ~30 секунд
- Расписание обновляется при каждом запросе к ICS ссылке
- Не нужно держать компьютер включённым
