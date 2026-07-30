import logging
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
from translations import text


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇫🇷 Français", callback_data="language:fr"),
                InlineKeyboardButton("🇬🇧 English", callback_data="language:en"),
            ]
        ]
    )


def main_menu(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text(language, "convert"), callback_data="menu:convert")],
            [
                InlineKeyboardButton(
                    text(language, "settings"), callback_data="menu:settings"
                ),
                InlineKeyboardButton(text(language, "help"), callback_data="menu:help"),
            ],
        ]
    )


def back_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text(language, "back"), callback_data="menu:back")]]
    )


def is_supported_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False

    host = (parsed.hostname or "").lower()
    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
    is_tiktok = host == "tiktok.com" or host.endswith(".tiktok.com")

    return parsed.scheme in {"http", "https"} and (
        host in youtube_hosts or is_tiktok
    )


def clear_conversion(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("step", "source_url", "source_file_id", "source_kind", "title"):
        context.user_data.pop(key, None)


async def accept_link(message, context: ContextTypes.DEFAULT_TYPE, language: str, value: str) -> None:
    if not is_supported_url(value):
        context.user_data["step"] = "link"
        await message.reply_text(text(language, "invalid_link"))
        return

    context.user_data["source_url"] = value.strip()
    context.user_data["step"] = "title"
    await message.reply_text(text(language, "link_accepted"))
    await message.reply_text(text(language, "ask_title"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    supplied_link = " ".join(context.args).strip() if context.args else ""

    if not language:
        if supplied_link:
            context.user_data["pending_link"] = supplied_link
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    if supplied_link:
        await accept_link(update.message, context, language, supplied_link)
        return

    clear_conversion(context)
    await update.message.reply_text(
        text(language, "welcome"), reply_markup=main_menu(language)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language", "fr")
    clear_conversion(context)
    await update.message.reply_text(
        text(language, "cancelled"), reply_markup=main_menu(language)
    )


async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query

    if query.data.startswith("language:"):
        await query.answer()
        language = query.data.split(":", maxsplit=1)[1]
        context.user_data["language"] = language
        pending_link = context.user_data.pop("pending_link", None)

        await query.edit_message_text(text(language, "language_saved"))
        if pending_link:
            await accept_link(query.message, context, language, pending_link)
        else:
            await query.message.reply_text(
                text(language, "welcome"), reply_markup=main_menu(language)
            )
        return

    language = context.user_data.get("language", "fr")

    if query.data == "menu:convert":
        await query.answer()
        clear_conversion(context)
        context.user_data["step"] = "link"
        await query.edit_message_text(
            text(language, "send_source"), reply_markup=back_keyboard(language)
        )
        return

    if query.data == "menu:settings":
        await query.answer()
        clear_conversion(context)
        await query.edit_message_text(
            text(language, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return

    if query.data == "menu:help":
        await query.answer()
        await query.edit_message_text(
            text(language, "help_text"), reply_markup=back_keyboard(language)
        )
        return

    if query.data == "menu:back":
        await query.answer()
        clear_conversion(context)
        await query.edit_message_text(
            text(language, "welcome"), reply_markup=main_menu(language)
        )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if not language:
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    media = update.message.audio or update.message.voice or update.message.document
    clear_conversion(context)
    context.user_data["source_file_id"] = media.file_id
    context.user_data["source_kind"] = "telegram_audio"
    context.user_data["step"] = "title"
    await update.message.reply_text(text(language, "audio_accepted"))
    await update.message.reply_text(text(language, "ask_title"))


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if not language:
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    media = update.message.video or update.message.video_note or update.message.document
    clear_conversion(context)
    context.user_data["source_file_id"] = media.file_id
    context.user_data["source_kind"] = "telegram_video"
    context.user_data["step"] = "title"
    await update.message.reply_text(text(language, "video_accepted"))
    await update.message.reply_text(text(language, "ask_title"))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if not language:
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    value = update.message.text.strip()
    step = context.user_data.get("step")

    if step == "link" or (not step and is_supported_url(value)):
        await accept_link(update.message, context, language, value)
        return

    if step == "title":
        if not value or len(value) > 100:
            await update.message.reply_text(text(language, "invalid_title"))
            return
        context.user_data["title"] = value
        context.user_data["step"] = "artist"
        await update.message.reply_text(text(language, "ask_artist"))
        return

    if step == "artist":
        if not value or len(value) > 100:
            await update.message.reply_text(text(language, "invalid_artist"))
            return

        title = context.user_data.get("title", "")
        clear_conversion(context)
        await update.message.reply_text(
            text(language, "ready", title=title, artist=value),
            reply_markup=main_menu(language),
        )
        return

    await update.message.reply_text(
        text(language, "use_menu"), reply_markup=main_menu(language)
    )


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO, handle_video
        )
    )
    application.add_handler(
        MessageHandler(
            filters.AUDIO | filters.VOICE | filters.Document.AUDIO, handle_audio
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    print("Saoxo Music est lancé. Appuie sur Ctrl+C pour l'arrêter.")
    application.run_polling()


if __name__ == "__main__":
    main()
