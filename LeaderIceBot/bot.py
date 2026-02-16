from __future__ import annotations

import asyncio
import io
import logging
import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from parser import ScheduleImage, get_schedule_images
from storage import Storage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Расписание", callback_data="schedule")]]
    )


def _images_to_media(images: List[ScheduleImage]) -> List[InputMediaPhoto]:
    media: List[InputMediaPhoto] = []
    for index, img in enumerate(images):
        photo = io.BytesIO(img.content)
        photo.name = f"schedule_{index + 1}.jpg"
        caption = "Текущее расписание льда" if index == 0 else None
        media.append(InputMediaPhoto(media=photo, caption=caption))
    return media


async def _get_images_async(target_url: str) -> List[ScheduleImage]:
    return await asyncio.to_thread(get_schedule_images, target_url)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    if update.effective_chat:
        storage.add_subscriber(update.effective_chat.id)

    await update.effective_message.reply_text(
        "Привет! Нажми кнопку, чтобы получить актуальное расписание.",
        reply_markup=_build_menu(),
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    if update.effective_chat:
        storage.remove_subscriber(update.effective_chat.id)
    await update.effective_message.reply_text("Ок, уведомления отключены.")


async def send_schedule(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    target_url: str = context.application.bot_data["target_url"]
    images = await _get_images_async(target_url)
    media = _images_to_media(images)
    await context.bot.send_media_group(chat_id=chat_id, media=media)


async def on_schedule_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await send_schedule(query.message.chat_id, context)
    except Exception as exc:
        logger.exception("Ошибка при отправке расписания: %s", exc)
        await query.message.reply_text("Не получилось получить расписание. Попробуй позже.")


async def hourly_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    target_url: str = context.application.bot_data["target_url"]

    try:
        images = await _get_images_async(target_url)
    except Exception as exc:
        logger.exception("Ошибка при проверке сайта: %s", exc)
        return

    old_hashes = storage.get_hashes()
    changed = False
    for img in images:
        old_hash = old_hashes.get(img.url)
        if old_hash != img.sha256:
            changed = True
        storage.upsert_hash(img.url, img.sha256)

    if not changed:
        return

    subscribers = storage.list_subscribers()
    if not subscribers:
        return

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    caption = f"Расписание обновилось ({now})"

    for chat_id in subscribers:
        try:
            media = _images_to_media(images)
            if media:
                media[0].caption = caption
            await context.bot.send_media_group(chat_id=chat_id, media=media)
        except Exception as exc:
            logger.exception("Не удалось отправить обновление в chat_id=%s: %s", chat_id, exc)


async def post_init(app: Application) -> None:
    interval_minutes: int = app.bot_data["interval_minutes"]
    app.job_queue.run_repeating(hourly_check, interval=interval_minutes * 60, first=10)


def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    target_url = os.getenv("TARGET_URL", "https://xn----htbdkifc7bc.xn--p1ai/")
    interval_minutes = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
    db_path = os.getenv("DB_PATH", "data/bot_state.db")

    storage = Storage(db_path)

    app = Application.builder().token(token).post_init(post_init).build()
    app.bot_data["storage"] = storage
    app.bot_data["target_url"] = target_url
    app.bot_data["interval_minutes"] = interval_minutes

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CallbackQueryHandler(on_schedule_clicked, pattern="^schedule$"))

    logger.info("Бот запущен. Интервал проверки: %s мин.", interval_minutes)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

