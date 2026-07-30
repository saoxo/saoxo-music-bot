import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if language:
        await update.message.reply_text(
            text(language, "welcome"), reply_markup=main_menu(language)
        )
        return

    await update.message.reply_text(
        "🌍 Choisis ta langue / Choose your language:",
        reply_markup=language_keyboard(),
    )


async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query

    if query.data.startswith("language:"):
        await query.answer()
        language = query.data.split(":", maxsplit=1)[1]
        context.user_data["language"] = language
        await query.edit_message_text(
            f"{text(language, 'language_saved')}\n\n{text(language, 'welcome')}",
            reply_markup=main_menu(language),
        )
        return

    language = context.user_data.get("language", "fr")

    if query.data == "menu:settings":
        await query.answer()
        await query.edit_message_text(
            text(language, "choose_language"),
            reply_markup=language_keyboard(),
        )
        return

    await query.answer(text(language, "coming_soon"), show_alert=True)


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Saoxo Music est lancé. Appuie sur Ctrl+C pour l'arrêter.")
    application.run_polling()


if __name__ == "__main__":
    main()
