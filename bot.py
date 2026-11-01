import asyncio
import html
import json
import logging
import os
import sqlite3
import time

import google.generativeai as genai
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart

# === Настройки (берём из переменных окружения) ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN or not GEMINI_API_KEY:
    raise SystemExit("Задай переменные окружения BOT_TOKEN и GEMINI_API_KEY")

MAX_MINUTES = 7 * 24 * 60  # максимум неделя
DB_PATH = "reminders.db"

# === Настройки ИИ ===
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel(
    model_name="gemini-3.6-flash",
    generation_config={"response_mime_type": "application/json"},
)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# === Инструкция для ИИ ===
SYSTEM_PROMPT = """
Ты — ассистент-парсер задач. Твоя единственная задача — извлечь из текста пользователя название задачи и время в МИНУТАХ от текущего момента.

Верни результат СТРОГО в формате JSON с ключами:
- "is_reminder": boolean (true, если это просьба о напоминании, false, если флуд или другой запрос)
- "task": string (название задачи)
- "minutes": integer (через сколько минут напомнить)

Примеры:
Текст: "Напомни через 2 часа сходить на пары"
JSON: {"is_reminder": true, "task": "сходить на пары", "minutes": 120}
Текст: "Какая сегодня погода?"
JSON: {"is_reminder": false, "task": "", "minutes": 0}
"""

# === База данных ===
def db_init() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                due_ts REAL NOT NULL
            )
            """
        )


def db_add(chat_id: int, task: str, due_ts: float) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO reminders (chat_id, task, due_ts) VALUES (?, ?, ?)",
            (chat_id, task, due_ts),
        )
        return cur.lastrowid


def db_delete(reminder_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))


def db_all() -> list[tuple[int, int, str, float]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT id, chat_id, task, due_ts FROM reminders"
        ).fetchall()


# === Отправка напоминаний ===
background_tasks: set[asyncio.Task] = set()


async def deliver(reminder_id: int, chat_id: int, task: str, due_ts: float) -> None:
    delay = max(0.0, due_ts - time.time())
    await asyncio.sleep(delay)
    try:
        await bot.send_message(chat_id, f"⏰ <b>НАПОМИНАНИЕ</b>: {html.escape(task)} ⏰")
        db_delete(reminder_id)
    except Exception:
        logging.exception("Не удалось отправить напоминание %s", reminder_id)


def schedule(reminder_id: int, chat_id: int, task: str, due_ts: float) -> None:
    t = asyncio.create_task(deliver(reminder_id, chat_id, task, due_ts))
    background_tasks.add(t)  # храним ссылку, чтобы задачу не удалил сборщик мусора
    t.add_done_callback(background_tasks.discard)


# === Хендлеры ===
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я твой умный помощник.\n"
        "Напиши мне что-то вроде «<b>Напомни через 5 минут проверить чайник</b>»"
    )


@dp.message(F.text)
async def process_reminder(message: types.Message):
    prompt = f"{SYSTEM_PROMPT}\nТекст пользователя: {message.text}"

    try:
        response = await ai_model.generate_content_async(prompt)
        data = json.loads(response.text)
        if not isinstance(data, dict):
            raise ValueError("ИИ вернул не объект JSON")
        is_reminder = bool(data.get("is_reminder"))
        task = str(data.get("task") or "").strip()
        minutes = int(data.get("minutes") or 0)
    except Exception:
        logging.exception("Ошибка при обработке запроса ИИ")
        await message.answer("Ошибка при обработке запроса ИИ. Попробуй ещё раз.")
        return

    if not is_reminder or not task or minutes <= 0:
        await message.answer(
            "Я бот-напоминатель. Напиши задачу и время "
            "(например: <b>Напомни через 10 минут выпить воду</b>)."
        )
        return

    if minutes > MAX_MINUTES:
        await message.answer("Слишком далеко! Максимум — 7 дней (10080 минут).")
        return

    due_ts = time.time() + minutes * 60
    reminder_id = db_add(message.chat.id, task, due_ts)
    schedule(reminder_id, message.chat.id, task, due_ts)

    await message.answer(
        f"Принято! Напомню про «{html.escape(task)}» через {minutes} мин."
    )


# === Запуск ===
async def main():
    logging.basicConfig(level=logging.INFO)
    db_init()

    # Восстанавливаем напоминания, которые не успели сработать до перезапуска
    for reminder_id, chat_id, task, due_ts in db_all():
        schedule(reminder_id, chat_id, task, due_ts)

    print("Бот успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())