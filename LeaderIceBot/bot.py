from __future__ import annotations

import asyncio
import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from telegram import (
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from parser import ScheduleImage, get_schedule_images
from storage import Storage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureConfig:
    button_text: str
    page_url: str
    filename_token: str
    max_images: int


FEATURE_ICE = "ice"
FEATURE_HOCKEY = "hockey"
FEATURE_FIGURE = "figure"


async def _get_images_async(
    page_url: str,
    filename_token: str,
    max_images: int,
) -> List[ScheduleImage]:
    return await asyncio.to_thread(
        get_schedule_images,
        page_url,
        filename_token,
        30,
        max_images,
    )


def _build_menu(features: Dict[str, FeatureConfig]) -> ReplyKeyboardMarkup:
    ice = features[FEATURE_ICE].button_text
    hockey = features[FEATURE_HOCKEY].button_text
    figure = features[FEATURE_FIGURE].button_text
    return ReplyKeyboardMarkup(
        [[KeyboardButton(ice), KeyboardButton(hockey)], [KeyboardButton(figure)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def _images_to_media(images: List[ScheduleImage]) -> List[InputMediaPhoto]:
    media: List[InputMediaPhoto] = []
    for index, img in enumerate(images):
        photo = io.BytesIO(img.content)
        photo.name = f"schedule_{index + 1}.jpg"
        caption = "Текущее расписание" if index == 0 else None
        media.append(InputMediaPhoto(media=photo, caption=caption))
    return media


async def _send_images(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    images: List[ScheduleImage],
    caption: str | None = None,
) -> None:
    if not images:
        raise RuntimeError("Нет изображений для отправки.")

    if len(images) == 1:
        photo = io.BytesIO(images[0].content)
        photo.name = "schedule_1.jpg"
        await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
        return

    media = _images_to_media(images)
    if caption and media:
        media[0].caption = caption
    await context.bot.send_media_group(chat_id=chat_id, media=media)


def _resolve_feature_by_text(
    text: str | None,
    features: Dict[str, FeatureConfig],
) -> Optional[str]:
    if not text:
        return None

    normalized = text.strip().lower()
    for key, cfg in features.items():
        if normalized == cfg.button_text.lower():
            return key

    if normalized == "/schedule":
        return FEATURE_ICE
    if normalized == "/hockey":
        return FEATURE_HOCKEY
    if normalized == "/figure":
        return FEATURE_FIGURE

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    features: Dict[str, FeatureConfig] = context.application.bot_data["features"]

    if update.effective_chat:
        storage.add_subscriber(update.effective_chat.id)

    await update.effective_message.reply_text(
        "Привет! Используй кнопку ниже: Расписание Льда, Хоккей или Фигурное катание.",
        reply_markup=_build_menu(features),
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    if update.effective_chat:
        storage.remove_subscriber(update.effective_chat.id)
    await update.effective_message.reply_text("Ок, уведомления отключены.")


async def send_feature(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    feature_key: str,
    caption: str | None = None,
) -> None:
    features: Dict[str, FeatureConfig] = context.application.bot_data["features"]
    cfg = features[feature_key]

    images = await _get_images_async(
        page_url=cfg.page_url,
        filename_token=cfg.filename_token,
        max_images=cfg.max_images,
    )
    await _send_images(chat_id=chat_id, context=context, images=images, caption=caption)


async def on_feature_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return

    features: Dict[str, FeatureConfig] = context.application.bot_data["features"]
    text = update.effective_message.text if update.effective_message else None
    feature_key = _resolve_feature_by_text(text, features)
    if not feature_key:
        return

    try:
        await send_feature(chat.id, context, feature_key)
    except Exception as exc:
        logger.exception("Ошибка при отправке расписания (%s): %s", feature_key, exc)
        if update.effective_message:
            await update.effective_message.reply_text(
                "Не получилось получить картинку. Попробуй позже."
            )


async def hourly_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    features: Dict[str, FeatureConfig] = context.application.bot_data["features"]
    ice_cfg = features[FEATURE_ICE]

    try:
        images = await _get_images_async(
            page_url=ice_cfg.page_url,
            filename_token=ice_cfg.filename_token,
            max_images=ice_cfg.max_images,
        )
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
    caption = f"Расписание льда обновилось ({now})"

    for chat_id in subscribers:
        try:
            await _send_images(chat_id=chat_id, context=context, images=images, caption=caption)
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

    features: Dict[str, FeatureConfig] = {
        FEATURE_ICE: FeatureConfig(
            button_text="Расписание Льда",
            page_url=target_url,
            filename_token="Расписание-льда",
            max_images=2,
        ),
        FEATURE_HOCKEY: FeatureConfig(
            button_text="Хоккей",
            page_url="https://xn----htbdkifc7bc.xn--p1ai/raspisanie-hc/",
            filename_token="Расписание-хоккей",
            max_images=1,
        ),
        FEATURE_FIGURE: FeatureConfig(
            button_text="Фигурное катание",
            page_url="https://xn----htbdkifc7bc.xn--p1ai/raspisanie-figure/",
            filename_token="Расписание_фигурное",
            max_images=1,
        ),
    }

    storage = Storage(db_path)

    app = Application.builder().token(token).post_init(post_init).build()
    app.bot_data["storage"] = storage
    app.bot_data["features"] = features
    app.bot_data["interval_minutes"] = interval_minutes

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("schedule", on_feature_request))
    app.add_handler(CommandHandler("hockey", on_feature_request))
    app.add_handler(CommandHandler("figure", on_feature_request))
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.Regex(r"^(Расписание Льда|Хоккей|Фигурное катание)$"),
            on_feature_request,
        )
    )

    logger.info("Бот запущен. Интервал проверки: %s мин.", interval_minutes)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
