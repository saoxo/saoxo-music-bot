TEXTS = {
    "fr": {
        "welcome": "🎵 Bienvenue sur Saoxo Music !\n\nQue souhaites-tu faire ?",
        "convert": "🎵 Convertir une musique",
        "settings": "⚙️ Paramètres",
        "help": "ℹ️ Aide",
        "coming_soon": "🚧 Cette fonction sera ajoutée prochainement.",
        "choose_language": "🌍 Choisis ta langue :",
        "language_saved": "✅ Langue définie sur Français.",
    },
    "en": {
        "welcome": "🎵 Welcome to Saoxo Music!\n\nWhat would you like to do?",
        "convert": "🎵 Convert a song",
        "settings": "⚙️ Settings",
        "help": "ℹ️ Help",
        "coming_soon": "🚧 This feature will be added soon.",
        "choose_language": "🌍 Choose your language:",
        "language_saved": "✅ Language set to English.",
    },
}


def text(language: str, key: str) -> str:
    return TEXTS.get(language, TEXTS["en"])[key]
