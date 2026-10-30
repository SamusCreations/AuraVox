"""
Rutas del proyecto en un solo lugar. Todo se resuelve desde la raíz de la
carpeta (la que tiene los .bat), así el proyecto se puede mover entero a
otro disco u otra máquina sin tocar nada.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuración editable (a mano o desde la interfaz web)
# AURAVOX_CONFIG: otra carpeta de configuración (para probar una segunda
# instancia sin tocar los perfiles, chats ni datos de la de uso diario).
CONFIG_DIR = os.environ.get("AURAVOX_CONFIG") or os.path.join(ROOT, "config")
ASSISTANTS_YAML = os.path.join(CONFIG_DIR, "assistants.yaml")
WAKE_WORDS_TXT = os.path.join(CONFIG_DIR, "wake_words.txt")
LANGUAGES_TXT = os.path.join(CONFIG_DIR, "languages.txt")
SPOTIFY_YAML = os.path.join(CONFIG_DIR, "spotify_config.yaml")

# Audio generado: respuestas del modo texto y muestras de las voces
AUDIO_DIR = os.path.join(ROOT, "audio")
VOICE_PREVIEWS_DIR = os.path.join(AUDIO_DIR, "voice_previews")

# Página de la interfaz web
WEBUI_STATIC_DIR = os.path.join(ROOT, "app", "webui", "static")

# Registro de la última ejecución de la interfaz web (se sobreescribe cada
# vez que arranca AuraVox.bat): para revisar errores después.
LOGS_DIR = os.path.join(ROOT, "logs")
WEBUI_LOG = os.path.join(LOGS_DIR, "webui_server.log")

# Ajustes de voz compartidos (modelo de Whisper, Qwen TTS) y voces clonadas
# (sus audios de referencia), editables desde "Ajustes compartidos".
VOICE_SETTINGS_YAML = os.path.join(CONFIG_DIR, "voice_settings.yaml")
CUSTOM_VOICES_DIR = os.path.join(CONFIG_DIR, "custom_voices")
QWEN_TTS_MODELS_DIR = os.path.join(ROOT, "cache", "qwen-tts")


def _ensure_config_defaults() -> None:
    """Inicializa archivos locales ignorados por Git a partir de sus plantillas
    *.example.yaml cuando se clona el repositorio por primera vez."""
    default_cfg_dir = os.path.join(ROOT, "config")
    pairs = (
        (ASSISTANTS_YAML, os.path.join(default_cfg_dir, "assistants.example.yaml")),
        (VOICE_SETTINGS_YAML, os.path.join(default_cfg_dir, "voice_settings.example.yaml")),
        (SPOTIFY_YAML, os.path.join(default_cfg_dir, "spotify_config.example.yaml")),
        (WAKE_WORDS_TXT, os.path.join(default_cfg_dir, "wake_words.example.txt")),
    )
    for target, template in pairs:
        if not os.path.exists(target) and os.path.isfile(template):
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(template, target)
            except OSError:
                pass


_ensure_config_defaults()
