"""
Motor genérico de asistente: sirve para JARVIS, BELLA o cualquier asistente
nuevo que agregues a assistants.yaml, sin necesitar un .py por asistente.

Modo texto (sin micrófono, para probar rápido):
    python assistant_engine.py jarvis
    python assistant_engine.py bella
    python assistant_engine.py <cualquier-nombre-de-assistants.yaml>

voice_loop.py (modo Alexa, con micrófono) usa `ask()` de este mismo módulo
para cada asistente que encuentre en assistants.yaml — ver ese archivo para
agregar uno nuevo sin tocar ningún .py.
"""
import os
import sys
import winsound

import requests

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import paths
from app.voice.supersonictts import release_shared_tts, CONFIG as _BASE_VOICE_CONFIG
from app.voice.qwen_tts import engine as _qwen_engine, make_voice
from app.core import plugins as _plugins
from app.core.assistant_common import (
    ask_with_tools,
    unload_ollama_model,
    load_assistants_config,
    ensure_models_installed,
)

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
CONFIG_PATH = paths.ASSISTANTS_YAML

# Las herramientas de siempre (búsqueda web y lugares, clima, Spotify) son
# plugins (carpeta plugins/, ver app/core/plugins.py): aquí, para los modos
# de consola, todas las que estén activadas. La interfaz web las pide por
# perfil (rol mínimo de cada plugin) con app/core/skills.py.
TOOLS = _plugins.tools(None)


def call_tool(name: str, arguments: dict) -> str:
    result = _plugins.call(name, arguments, None)
    return result if result is not None else f"Unknown tool {name}."


def get_all_configs() -> dict:
    """Recarga assistants.yaml. Es una lectura barata (un archivo de texto
    chico) así que no hace falta cachearla — asegura que un cambio en el
    archivo se vea reflejado la próxima vez que se llame a esta función,
    sin tener que reiniciar el proceso a medias."""
    return load_assistants_config(CONFIG_PATH)


def get_assistant_config(name: str) -> dict:
    configs = get_all_configs()
    if name not in configs:
        disponibles = ", ".join(sorted(configs)) or "(ninguno definido en assistants.yaml)"
        raise KeyError(f"No existe el asistente '{name}' en assistants.yaml. Disponibles: {disponibles}")
    return configs[name]


def voice_config_for(cfg: dict) -> dict:
    return {**_BASE_VOICE_CONFIG, "voice": cfg["voice"], "speed": cfg["speed"], "language": cfg["language"]}


def reply_wav_for(name: str) -> str:
    return os.path.join(paths.AUDIO_DIR, f"{name}_reply.wav")


def ask(name: str, history: list, on_tool_call=None, reply_lang: str = None, cfg: dict = None, style: str = "voice",
        on_text=None) -> str:
    """Pide una respuesta al asistente `name` (debe existir en
    assistants.yaml). Si ya tienes `cfg` cargado (voice_loop.py lo hace una
    sola vez al arrancar), pásalo para no releer el archivo en cada turno.

    Sin `reply_lang` (modo texto, switch_model.py) responde en el `language`
    del asistente — si no, un asistente configurado en inglés respondería
    en español por la regla por defecto de shared_context.

    `style`: "voice" (voice_loop.py, respuestas cortas y naturales) o
    "text" (modo texto, más detalladas si hace falta) — ver
    assistant_common.RESPONSE_STYLES."""
    cfg = cfg or get_assistant_config(name)
    reply_lang = reply_lang or cfg["language"]
    return ask_with_tools(
        OLLAMA_URL,
        cfg["base_model"],
        cfg["personality"],
        history,
        TOOLS,
        call_tool,
        max_tool_rounds=cfg["max_tool_rounds"],
        fallback_message=cfg["fallback_message"],
        on_tool_call=on_tool_call,
        reply_lang=reply_lang,
        shared_context=cfg.get("shared_context"),
        temperature=cfg["temperature"],
        top_k=cfg["top_k"],
        top_p=cfg["top_p"],
        assistant_name=cfg["label"],
        style=style,
        on_text=on_text,
    )


def run_text_mode(name: str):
    """Modo texto interactivo (sin micrófono) para el asistente `name`."""
    cfg = get_assistant_config(name)
    ensure_models_installed({name: cfg})
    voice = make_voice(voice_config_for(cfg))
    reply_wav = reply_wav_for(name)
    history = []

    def _announce_search(tool_name):
        if tool_name == "web_search":
            wav_path = voice.speak(cfg["search_announcement"], reply_wav)
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)

    print(f"{cfg['label']} ready. Type your message (or 'exit' to quit).\n")
    try:
        while True:
            try:
                text = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("salir", "exit", "quit", ""):
                break

            history.append({"role": "user", "content": text})

            try:
                reply = ask(name, history, on_tool_call=_announce_search, cfg=cfg, style="text")
            except requests.exceptions.ConnectionError:
                print("Cannot connect to Ollama. Is the service running ('ollama serve')?")
                history.pop()
                continue
            except requests.exceptions.RequestException as e:
                print(f"(Ollama request failed: {e}. Please try again.)")
                history.pop()
                continue

            history.append({"role": "assistant", "content": reply})
            history[:] = history[-cfg["max_history"]:]

            print(f"{cfg['label']}> {reply}")
            wav_path = voice.speak(reply, reply_wav)
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    finally:
        print("Unloading model from Ollama...")
        unload_ollama_model(cfg["base_model"])
        voice.release()
        release_shared_tts()
        _qwen_engine().release()

    print("Goodbye.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        try:
            disponibles = ", ".join(sorted(get_all_configs()))
        except Exception:
            disponibles = "(could not read assistants.yaml)"
        print(f"Usage: extras\\run_assistant.bat <name>\nAvailable: {disponibles}")
        sys.exit(1)
    run_text_mode(sys.argv[1])
