import asyncio
import hashlib
import logging
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import deno
from imageio_ffmpeg import get_ffmpeg_exe
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
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
from yt_dlp import YoutubeDL


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)

MAX_TELEGRAM_DOWNLOAD_SIZE = 20 * 1024 * 1024
MAX_TELEGRAM_UPLOAD_SIZE = 50 * 1024 * 1024


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


def cover_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text(language, "add_cover"), callback_data="cover:add")],
            [InlineKeyboardButton(text(language, "skip_cover"), callback_data="cover:skip")],
        ]
    )


def skip_cover_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text(language, "skip_cover"), callback_data="cover:skip")]]
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
    for key in (
        "step",
        "source_url",
        "source_file_id",
        "source_kind",
        "title",
        "artist",
        "cover_file_id",
    ):
        context.user_data.pop(key, None)


def find_downloaded_media(temporary_path: Path) -> Path:
    candidates = [
        path
        for path in temporary_path.iterdir()
        if path.is_file()
        and path.name.startswith("download.")
        and not path.name.endswith(".part")
    ]
    if not candidates:
        raise RuntimeError("yt-dlp did not create a media file")

    return max(candidates, key=lambda path: path.stat().st_size)


def media_has_audio(media_path: Path) -> bool:
    result = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(media_path),
            "-map",
            "0:a:0",
            "-frames:a",
            "1",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def download_link_media_sync(source_url: str, temporary_path: Path) -> Path:
    deno_directory = str(Path(deno.find_deno_bin()).parent)
    current_path = os.environ.get("PATH", "")
    if deno_directory not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{deno_directory}{os.pathsep}{current_path}"

    def download(extractor_args=None) -> Path:
        options = {
            "format": (
                "bestaudio[acodec!=none]/best[acodec!=none]/bestaudio/best"
            ),
            "outtmpl": str(temporary_path / "download.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "verbose": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "overwrites": True,
            "cachedir": False,
            "max_filesize": 100 * 1024 * 1024,
            "ffmpeg_location": get_ffmpeg_exe(),
        }
        pot_provider_home = os.getenv("POT_PROVIDER_HOME")
        if pot_provider_home:
            options["extractor_args"] = {
                "youtube": {
                    "player_client": ["mweb"],
                },
                "youtubepot-bgutilscript": {
                    "server_home": [pot_provider_home],
                }
            }
        if extractor_args:
            options.setdefault("extractor_args", {}).update(extractor_args)

        with YoutubeDL(options) as downloader:
            downloader.extract_info(source_url, download=True)

        return find_downloaded_media(temporary_path)

    input_path = download()
    if media_has_audio(input_path):
        return input_path

    host = (urlparse(source_url).hostname or "").lower()
    is_tiktok = host == "tiktok.com" or host.endswith(".tiktok.com")
    if is_tiktok:
        for path in temporary_path.glob("download.*"):
            if path.is_file():
                path.unlink()

        input_path = download({"tiktok": {"app_info": [""]}})
        if media_has_audio(input_path):
            return input_path

    raise RuntimeError("The downloaded media does not contain an audio stream")


async def download_link_media(source_url: str, temporary_path: Path) -> Path:
    return await asyncio.to_thread(
        download_link_media_sync,
        source_url,
        temporary_path,
    )


def safe_filename(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " ._-" else "_"
        for character in value
    ).strip(" .")
    return (cleaned or "saoxo-music")[:80]


async def run_ffmpeg(*arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        get_ffmpeg_exe(),
        *arguments,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, error_output = await process.communicate()

    if process.returncode != 0:
        error_details = error_output.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError(f"FFmpeg failed: {error_details}")


async def convert_and_send(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
    title: str,
    artist: str,
) -> None:
    status_message = await message.reply_text(text(language, "processing"))
    source_file_id = context.user_data.get("source_file_id")
    cover_file_id = context.user_data.get("cover_file_id")

    try:
        with TemporaryDirectory(prefix="saoxo_music_") as temporary_directory:
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "source_media"
            output_path = temporary_path / "converted.mp3"
            thumbnail_path = None

            if source_file_id:
                telegram_file = await context.bot.get_file(source_file_id)
                await telegram_file.download_to_drive(custom_path=input_path)
            else:
                source_url = context.user_data.get("source_url")
                if not source_url:
                    raise RuntimeError("Missing source URL")
                input_path = await download_link_media(source_url, temporary_path)

            ffmpeg_arguments = ["-y", "-i", str(input_path)]

            if cover_file_id:
                cover_input_path = temporary_path / "cover_source"
                thumbnail_path = temporary_path / "cover.jpg"
                telegram_cover = await context.bot.get_file(cover_file_id)
                await telegram_cover.download_to_drive(custom_path=cover_input_path)

                await run_ffmpeg(
                    "-y",
                    "-i",
                    str(cover_input_path),
                    "-vf",
                    "scale=320:320:force_original_aspect_ratio=decrease,"
                    "pad=320:320:(ow-iw)/2:(oh-ih)/2:black",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "7",
                    str(thumbnail_path),
                )

                ffmpeg_arguments.extend(
                    [
                        "-i",
                        str(thumbnail_path),
                        "-map",
                        "0:a:0",
                        "-map",
                        "1:v:0",
                        "-codec:v",
                        "mjpeg",
                        "-disposition:v:0",
                        "attached_pic",
                    ]
                )
            else:
                ffmpeg_arguments.extend(["-map", "0:a:0", "-vn"])

            ffmpeg_arguments.extend(
                [
                    "-map_metadata",
                    "-1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    "-metadata",
                    f"title={title}",
                    "-metadata",
                    f"artist={artist}",
                    "-id3v2_version",
                    "3",
                    str(output_path),
                ]
            )
            await run_ffmpeg(*ffmpeg_arguments)

            if not output_path.exists():
                raise RuntimeError("FFmpeg did not create the MP3 file")
            if output_path.stat().st_size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError("The converted MP3 exceeds Telegram upload limits")

            output_name = f"{safe_filename(title)}.mp3"
            with output_path.open("rb") as audio_file:
                audio_input = InputFile(
                    audio_file,
                    filename=output_name,
                    read_file_handle=False,
                )

                if thumbnail_path:
                    with thumbnail_path.open("rb") as thumbnail_file:
                        await message.reply_audio(
                            audio=audio_input,
                            thumbnail=InputFile(
                                thumbnail_file,
                                filename="cover.jpg",
                                read_file_handle=False,
                            ),
                            title=title,
                            performer=artist,
                        )
                else:
                    await message.reply_audio(
                        audio=audio_input,
                        title=title,
                        performer=artist,
                    )

        await status_message.edit_text(text(language, "conversion_sent"))
    except Exception:
        logging.exception("Telegram media conversion failed")
        await status_message.edit_text(text(language, "conversion_error"))
    finally:
        clear_conversion(context)


async def finish_source(message, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    title = context.user_data.get("title", "")
    artist = context.user_data.get("artist", "")
    source_kind = context.user_data.get("source_kind")

    if source_kind in {"telegram_audio", "telegram_video", "link"}:
        await convert_and_send(message, context, language, title, artist)
    else:
        clear_conversion(context)
        await message.reply_text(text(language, "ready", title=title, artist=artist))

    await message.reply_text(
        text(language, "welcome"), reply_markup=main_menu(language)
    )


async def accept_link(message, context: ContextTypes.DEFAULT_TYPE, language: str, value: str) -> None:
    if not is_supported_url(value):
        context.user_data["step"] = "link"
        await message.reply_text(text(language, "invalid_link"))
        return

    context.user_data["source_url"] = value.strip()
    context.user_data["source_kind"] = "link"
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


    if query.data == "cover:add":
        await query.answer()
        context.user_data["step"] = "cover_image"
        await query.edit_message_text(
            text(language, "ask_cover_image"),
            reply_markup=skip_cover_keyboard(language),
        )
        return

    if query.data == "cover:skip":
        await query.answer()
        context.user_data.pop("cover_file_id", None)
        await query.edit_message_text(text(language, "cover_skipped"))
        await finish_source(query.message, context, language)
        return

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
    if media.file_size and media.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

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
    if media.file_size and media.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

    clear_conversion(context)
    context.user_data["source_file_id"] = media.file_id
    context.user_data["source_kind"] = "telegram_video"
    context.user_data["step"] = "title"
    await update.message.reply_text(text(language, "video_accepted"))
    await update.message.reply_text(text(language, "ask_title"))


async def handle_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if not language:
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    if context.user_data.get("step") != "cover_image":
        await update.message.reply_text(
            text(language, "use_menu"), reply_markup=main_menu(language)
        )
        return

    image = update.message.photo[-1] if update.message.photo else update.message.document
    if image.file_size and image.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

    context.user_data["cover_file_id"] = image.file_id
    await update.message.reply_text(text(language, "cover_received"))
    await finish_source(update.message, context, language)


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

        context.user_data["artist"] = value
        context.user_data["step"] = "cover_choice"
        await update.message.reply_text(
            text(language, "ask_cover"),
            reply_markup=cover_keyboard(language),
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
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_cover)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    public_domain = (
        os.getenv("KOYEB_PUBLIC_DOMAIN")
        or os.getenv("RENDER_EXTERNAL_HOSTNAME")
        or os.getenv("RENDER_EXTERNAL_URL")
    )
    if public_domain:
        public_domain = (
            public_domain.removeprefix("https://")
            .removeprefix("http://")
            .strip("/")
        )
        webhook_path = hashlib.sha256(
            f"path:{BOT_TOKEN}".encode("utf-8")
        ).hexdigest()
        webhook_secret = hashlib.sha256(
            f"secret:{BOT_TOKEN}".encode("utf-8")
        ).hexdigest()
        port = int(os.getenv("PORT", "8000"))

        hosting_provider = "Render" if os.getenv("RENDER_SERVICE_ID") else "Koyeb"
        print(f"Saoxo Music est lancé sur {hosting_provider} avec un webhook.")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=f"https://{public_domain}/{webhook_path}",
            secret_token=webhook_secret,
        )
    else:
        print("Saoxo Music est lancé. Appuie sur Ctrl+C pour l'arrêter.")
        application.run_polling()


if __name__ == "__main__":
    main()
import asyncio
import hashlib
import logging
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import deno
from imageio_ffmpeg import get_ffmpeg_exe
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
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
from yt_dlp import YoutubeDL


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
)

MAX_TELEGRAM_DOWNLOAD_SIZE = 20 * 1024 * 1024
MAX_TELEGRAM_UPLOAD_SIZE = 50 * 1024 * 1024


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


def cover_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text(language, "add_cover"), callback_data="cover:add")],
            [InlineKeyboardButton(text(language, "skip_cover"), callback_data="cover:skip")],
        ]
    )


def skip_cover_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text(language, "skip_cover"), callback_data="cover:skip")]]
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
    for key in (
        "step",
        "source_url",
        "source_file_id",
        "source_kind",
        "title",
        "artist",
        "cover_file_id",
    ):
        context.user_data.pop(key, None)


def find_downloaded_media(temporary_path: Path) -> Path:
    candidates = [
        path
        for path in temporary_path.iterdir()
        if path.is_file()
        and path.name.startswith("download.")
        and not path.name.endswith(".part")
    ]
    if not candidates:
        raise RuntimeError("yt-dlp did not create a media file")

    return max(candidates, key=lambda path: path.stat().st_size)


def media_has_audio(media_path: Path) -> bool:
    result = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(media_path),
            "-map",
            "0:a:0",
            "-frames:a",
            "1",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def download_link_media_sync(source_url: str, temporary_path: Path) -> Path:
    deno_directory = str(Path(deno.find_deno_bin()).parent)
    current_path = os.environ.get("PATH", "")
    if deno_directory not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{deno_directory}{os.pathsep}{current_path}"

    def download(extractor_args=None) -> Path:
        options = {
            "format": (
                "bestaudio[acodec!=none]/best[acodec!=none]/bestaudio/best"
            ),
            "outtmpl": str(temporary_path / "download.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "overwrites": True,
            "cachedir": False,
            "max_filesize": 100 * 1024 * 1024,
            "ffmpeg_location": get_ffmpeg_exe(),
        }
        pot_provider_home = os.getenv("POT_PROVIDER_HOME")
        if pot_provider_home:
            options["extractor_args"] = {
                "youtube": {
                    "player_client": ["mweb"],
                },
                "youtubepot-bgutilscript": {
                    "server_home": [pot_provider_home],
                }
            }
        if extractor_args:
            options.setdefault("extractor_args", {}).update(extractor_args)

        with YoutubeDL(options) as downloader:
            downloader.extract_info(source_url, download=True)

        return find_downloaded_media(temporary_path)

    input_path = download()
    if media_has_audio(input_path):
        return input_path

    host = (urlparse(source_url).hostname or "").lower()
    is_tiktok = host == "tiktok.com" or host.endswith(".tiktok.com")
    if is_tiktok:
        for path in temporary_path.glob("download.*"):
            if path.is_file():
                path.unlink()

        input_path = download({"tiktok": {"app_info": [""]}})
        if media_has_audio(input_path):
            return input_path

    raise RuntimeError("The downloaded media does not contain an audio stream")


async def download_link_media(source_url: str, temporary_path: Path) -> Path:
    return await asyncio.to_thread(
        download_link_media_sync,
        source_url,
        temporary_path,
    )


def safe_filename(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " ._-" else "_"
        for character in value
    ).strip(" .")
    return (cleaned or "saoxo-music")[:80]


async def run_ffmpeg(*arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        get_ffmpeg_exe(),
        *arguments,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, error_output = await process.communicate()

    if process.returncode != 0:
        error_details = error_output.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError(f"FFmpeg failed: {error_details}")


async def convert_and_send(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
    title: str,
    artist: str,
) -> None:
    status_message = await message.reply_text(text(language, "processing"))
    source_file_id = context.user_data.get("source_file_id")
    cover_file_id = context.user_data.get("cover_file_id")

    try:
        with TemporaryDirectory(prefix="saoxo_music_") as temporary_directory:
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "source_media"
            output_path = temporary_path / "converted.mp3"
            thumbnail_path = None

            if source_file_id:
                telegram_file = await context.bot.get_file(source_file_id)
                await telegram_file.download_to_drive(custom_path=input_path)
            else:
                source_url = context.user_data.get("source_url")
                if not source_url:
                    raise RuntimeError("Missing source URL")
                input_path = await download_link_media(source_url, temporary_path)

            ffmpeg_arguments = ["-y", "-i", str(input_path)]

            if cover_file_id:
                cover_input_path = temporary_path / "cover_source"
                thumbnail_path = temporary_path / "cover.jpg"
                telegram_cover = await context.bot.get_file(cover_file_id)
                await telegram_cover.download_to_drive(custom_path=cover_input_path)

                await run_ffmpeg(
                    "-y",
                    "-i",
                    str(cover_input_path),
                    "-vf",
                    "scale=320:320:force_original_aspect_ratio=decrease,"
                    "pad=320:320:(ow-iw)/2:(oh-ih)/2:black",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "7",
                    str(thumbnail_path),
                )

                ffmpeg_arguments.extend(
                    [
                        "-i",
                        str(thumbnail_path),
                        "-map",
                        "0:a:0",
                        "-map",
                        "1:v:0",
                        "-codec:v",
                        "mjpeg",
                        "-disposition:v:0",
                        "attached_pic",
                    ]
                )
            else:
                ffmpeg_arguments.extend(["-map", "0:a:0", "-vn"])

            ffmpeg_arguments.extend(
                [
                    "-map_metadata",
                    "-1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    "-metadata",
                    f"title={title}",
                    "-metadata",
                    f"artist={artist}",
                    "-id3v2_version",
                    "3",
                    str(output_path),
                ]
            )
            await run_ffmpeg(*ffmpeg_arguments)

            if not output_path.exists():
                raise RuntimeError("FFmpeg did not create the MP3 file")
            if output_path.stat().st_size > MAX_TELEGRAM_UPLOAD_SIZE:
                raise RuntimeError("The converted MP3 exceeds Telegram upload limits")

            output_name = f"{safe_filename(title)}.mp3"
            with output_path.open("rb") as audio_file:
                audio_input = InputFile(
                    audio_file,
                    filename=output_name,
                    read_file_handle=False,
                )

                if thumbnail_path:
                    with thumbnail_path.open("rb") as thumbnail_file:
                        await message.reply_audio(
                            audio=audio_input,
                            thumbnail=InputFile(
                                thumbnail_file,
                                filename="cover.jpg",
                                read_file_handle=False,
                            ),
                            title=title,
                            performer=artist,
                        )
                else:
                    await message.reply_audio(
                        audio=audio_input,
                        title=title,
                        performer=artist,
                    )

        await status_message.edit_text(text(language, "conversion_sent"))
    except Exception:
        logging.exception("Telegram media conversion failed")
        await status_message.edit_text(text(language, "conversion_error"))
    finally:
        clear_conversion(context)


async def finish_source(message, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    title = context.user_data.get("title", "")
    artist = context.user_data.get("artist", "")
    source_kind = context.user_data.get("source_kind")

    if source_kind in {"telegram_audio", "telegram_video", "link"}:
        await convert_and_send(message, context, language, title, artist)
    else:
        clear_conversion(context)
        await message.reply_text(text(language, "ready", title=title, artist=artist))

    await message.reply_text(
        text(language, "welcome"), reply_markup=main_menu(language)
    )


async def accept_link(message, context: ContextTypes.DEFAULT_TYPE, language: str, value: str) -> None:
    if not is_supported_url(value):
        context.user_data["step"] = "link"
        await message.reply_text(text(language, "invalid_link"))
        return

    context.user_data["source_url"] = value.strip()
    context.user_data["source_kind"] = "link"
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


    if query.data == "cover:add":
        await query.answer()
        context.user_data["step"] = "cover_image"
        await query.edit_message_text(
            text(language, "ask_cover_image"),
            reply_markup=skip_cover_keyboard(language),
        )
        return

    if query.data == "cover:skip":
        await query.answer()
        context.user_data.pop("cover_file_id", None)
        await query.edit_message_text(text(language, "cover_skipped"))
        await finish_source(query.message, context, language)
        return

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
    if media.file_size and media.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

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
    if media.file_size and media.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

    clear_conversion(context)
    context.user_data["source_file_id"] = media.file_id
    context.user_data["source_kind"] = "telegram_video"
    context.user_data["step"] = "title"
    await update.message.reply_text(text(language, "video_accepted"))
    await update.message.reply_text(text(language, "ask_title"))


async def handle_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = context.user_data.get("language")
    if not language:
        await update.message.reply_text(
            "🌍 Choisis ta langue / Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    if context.user_data.get("step") != "cover_image":
        await update.message.reply_text(
            text(language, "use_menu"), reply_markup=main_menu(language)
        )
        return

    image = update.message.photo[-1] if update.message.photo else update.message.document
    if image.file_size and image.file_size > MAX_TELEGRAM_DOWNLOAD_SIZE:
        await update.message.reply_text(text(language, "file_too_large"))
        return

    context.user_data["cover_file_id"] = image.file_id
    await update.message.reply_text(text(language, "cover_received"))
    await finish_source(update.message, context, language)


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

        context.user_data["artist"] = value
        context.user_data["step"] = "cover_choice"
        await update.message.reply_text(
            text(language, "ask_cover"),
            reply_markup=cover_keyboard(language),
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
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_cover)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    public_domain = (
        os.getenv("KOYEB_PUBLIC_DOMAIN")
        or os.getenv("RENDER_EXTERNAL_HOSTNAME")
        or os.getenv("RENDER_EXTERNAL_URL")
    )
    if public_domain:
        public_domain = (
            public_domain.removeprefix("https://")
            .removeprefix("http://")
            .strip("/")
        )
        webhook_path = hashlib.sha256(
            f"path:{BOT_TOKEN}".encode("utf-8")
        ).hexdigest()
        webhook_secret = hashlib.sha256(
            f"secret:{BOT_TOKEN}".encode("utf-8")
        ).hexdigest()
        port = int(os.getenv("PORT", "8000"))

        hosting_provider = "Render" if os.getenv("RENDER_SERVICE_ID") else "Koyeb"
        print(f"Saoxo Music est lancé sur {hosting_provider} avec un webhook.")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=f"https://{public_domain}/{webhook_path}",
            secret_token=webhook_secret,
        )
    else:
        print("Saoxo Music est lancé. Appuie sur Ctrl+C pour l'arrêter.")
        application.run_polling()


if __name__ == "__main__":
    main()
