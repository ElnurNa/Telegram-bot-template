A Telegram bot for creating reminders using natural language. A user might type, for example, "Remind me to drink water in 10 minutes," and Gemini identifies both the task and the time. The bot stores the reminder in an SQLite database and sends a message at the scheduled time. If the bot is restarted, the reminders are restored from the database.

**The environment variables `BOT_TOKEN` and `GEMINI_API_KEY` are required for operation.**

...................................................................................................................................................................................................

Telegram-бот для создания напоминаний на естественном языке. Пользователь пишет, например: «Напомни через 10 минут выпить воду», а Gemini определяет задачу и время. Бот сохраняет напоминание в SQLite и отправляет сообщение в нужное время. После перезапуска бота напоминания восстанавливаются из базы данных.

**Для работы нужны переменные окружения BOT_TOKEN и GEMINI_API_KEY.**
