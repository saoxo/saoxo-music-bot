TEXTS = {
    "fr": {
        "welcome": """🎵 Bienvenue sur Saoxo Music !

Que souhaites-tu faire ?""",
        "convert": "🎵 Convertir une musique",
        "settings": "⚙️ Paramètres",
        "help": "ℹ️ Aide",
        "back": "⬅️ Retour au menu",
        "choose_language": "🌍 Choisis ta langue :",
        "language_saved": "✅ Langue définie sur Français.",
        "send_source": """🔗 Envoie un lien YouTube ou TikTok, ou transfère-moi un audio ou une vidéo Telegram.

Tu peux annuler avec /cancel.""",
        "invalid_link": "❌ Ce lien n'est pas reconnu. Envoie un lien YouTube ou TikTok valide.",
        "link_accepted": "✅ Lien reconnu.",
        "audio_accepted": "✅ Audio Telegram reçu.",
        "video_accepted": "✅ Vidéo Telegram reçue. Son audio sera extrait.",
        "processing": "⏳ Téléchargement et conversion en MP3...",
        "conversion_sent": "✅ Conversion terminée et fichier envoyé.",
        "conversion_error": "❌ La conversion a échoué. Réessaie avec un autre fichier.",
        "file_too_large": "❌ Ce fichier dépasse la limite de téléchargement de 20 Mo de Telegram.",
        "ask_title": "✏️ Quel titre veux-tu donner à cette musique ?",
        "invalid_title": "❌ Le titre doit contenir entre 1 et 100 caractères.",
        "ask_artist": "👤 Quel nom d'artiste veux-tu afficher ?",
        "invalid_artist": "❌ Le nom d'artiste doit contenir entre 1 et 100 caractères.",
        "ask_cover": "🖼️ Veux-tu ajouter une cover ? C’est optionnel.",
        "add_cover": "🖼️ Ajouter une cover",
        "skip_cover": "⏭️ Sans cover",
        "ask_cover_image": "🖼️ Envoie maintenant une image pour la cover.",
        "cover_received": "✅ Cover reçue.",
        "cover_skipped": "⏭️ Conversion sans cover.",
        "ready": """✅ Informations enregistrées !

🎵 Titre : {title}
👤 Artiste : {artist}

La conversion sera ajoutée à la prochaine étape.""",
        "help_text": """ℹ️ Utilisation

• Appuie sur Convertir une musique puis envoie un lien YouTube ou TikTok.
• Tu peux aussi transférer un audio, un vocal ou une vidéo Telegram.
• Tu peux écrire /start suivi d'un lien.
• Utilise /cancel pour annuler.""",
        "cancelled": "✅ Conversion annulée.",
        "use_menu": "Choisis une option dans le menu ou envoie un lien compatible.",
    },
    "en": {
        "welcome": """🎵 Welcome to Saoxo Music!

What would you like to do?""",
        "convert": "🎵 Convert a song",
        "settings": "⚙️ Settings",
        "help": "ℹ️ Help",
        "back": "⬅️ Back to menu",
        "choose_language": "🌍 Choose your language:",
        "language_saved": "✅ Language set to English.",
        "send_source": """🔗 Send a YouTube or TikTok link, or forward a Telegram audio or video.

You can cancel with /cancel.""",
        "invalid_link": "❌ This link is not supported. Send a valid YouTube or TikTok link.",
        "link_accepted": "✅ Link recognized.",
        "audio_accepted": "✅ Telegram audio received.",
        "video_accepted": "✅ Telegram video received. Its audio will be extracted.",
        "processing": "⏳ Downloading and converting to MP3...",
        "conversion_sent": "✅ Conversion complete and file sent.",
        "conversion_error": "❌ Conversion failed. Please try another file.",
        "file_too_large": "❌ This file exceeds Telegram’s 20 MB download limit.",
        "ask_title": "✏️ What title would you like to use for this song?",
        "invalid_title": "❌ The title must contain between 1 and 100 characters.",
        "ask_artist": "👤 What artist name would you like to display?",
        "invalid_artist": "❌ The artist name must contain between 1 and 100 characters.",
        "ask_cover": "🖼️ Would you like to add cover art? This is optional.",
        "add_cover": "🖼️ Add cover art",
        "skip_cover": "⏭️ No cover",
        "ask_cover_image": "🖼️ Send an image for the cover now.",
        "cover_received": "✅ Cover received.",
        "cover_skipped": "⏭️ Converting without cover.",
        "ready": """✅ Information saved!

🎵 Title: {title}
👤 Artist: {artist}

Audio conversion will be added in the next step.""",
        "help_text": """ℹ️ How to use the bot

• Tap Convert a song, then send a YouTube or TikTok link.
• You can also forward a Telegram audio file, voice message, or video.
• You can type /start followed by a link.
• Use /cancel to cancel.""",
        "cancelled": "✅ Conversion cancelled.",
        "use_menu": "Choose an option from the menu or send a supported link.",
    },
}


def text(language: str, key: str, **values: str) -> str:
    message = TEXTS.get(language, TEXTS["en"])[key]
    return message.format(**values)
