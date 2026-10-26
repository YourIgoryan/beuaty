"""Single Render web service: FastAPI health API + Telegram polling bot."""
import asyncio
import logging

from app.api import app
from app.bot import bot, dp, reminder_loop

logger = logging.getLogger(__name__)


async def run_bot_forever() -> None:
    """Restart polling after transient Telegram/network failures instead of silently dying."""
    delay = 5
    while True:
        try:
            logger.info("Starting Telegram polling")
            await dp.start_polling(bot, close_bot_session=False)
            delay = 5
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram polling stopped; retrying in %s seconds", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


@app.on_event("startup")
async def start_background_tasks() -> None:
    app.state.bot_task = asyncio.create_task(run_bot_forever(), name="telegram-bot")
    app.state.reminder_task = asyncio.create_task(reminder_loop(), name="booking-reminders")


@app.on_event("shutdown")
async def stop_background_tasks() -> None:
    tasks = [getattr(app.state, name, None) for name in ("bot_task", "reminder_task")]
    for task in tasks:
        if task:
            task.cancel()
    for task in tasks:
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
    await bot.session.close()
