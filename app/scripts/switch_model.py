"""
Cambia el modelo de IA (LLM) base detrás de cualquier asistente de
assistants.yaml.

Descarga el modelo nuevo si hace falta ("ollama pull"), actualiza el campo
"base_model" del asistente elegido en assistants.yaml (solo esa línea —
comentarios y el resto de la configuración quedan intactos) y hace una
prueba rápida. Ya no usa Modelfiles ni "ollama create": cada asistente
llama directo al modelo base en cada petición (ver assistant_common.py),
así que cambiar de modelo es solo cambiar ese nombre.

Ejecutar: switch_model.bat (o "python switch_model.py" directamente).
Requiere que Ollama esté corriendo.
"""
import os
import re
import subprocess
import sys

import requests
import yaml

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.assistant_common import ollama_installed_models, model_is_installed, NON_ASSISTANT_KEYS
from app.paths import ASSISTANTS_YAML as CONFIG_PATH
OLLAMA_SHOW_URL = "http://127.0.0.1:11434/api/show"

_BASE_MODEL_LINE_RE = re.compile(r"(?m)^(\s*base_model:\s*).*$")


def _read_raw_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_assistants() -> list:
    # "shared_context"/"user_context" son configuración de nivel superior
    # compartida por todos los asistentes, no un asistente en sí — se
    # excluyen para no ofrecerlas como opción.
    return [name for name in _read_raw_config() if name not in NON_ASSISTANT_KEYS]


def current_base_model(name: str) -> str:
    return (_read_raw_config().get(name) or {}).get("base_model", "?")


def pull_model(name: str):
    print(f"\nDescargando '{name}' desde Ollama (puede tardar según el tamaño)...\n")
    result = subprocess.run(["ollama", "pull", name])
    if result.returncode != 0:
        print(
            f"\nNo se pudo descargar '{name}'. Revisa que el nombre sea exacto "
            "(tal como aparece en 'ollama list' o en https://ollama.com/library) e intenta de nuevo."
        )
        sys.exit(1)


def show_model(name: str) -> dict:
    try:
        r = requests.post(OLLAMA_SHOW_URL, json={"model": name}, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException:
        return {}


def warn_capabilities(name: str):
    caps = show_model(name).get("capabilities", [])
    if not caps:
        print(f"\n(No pude leer las capacidades de '{name}' desde Ollama; sigo de todas formas.)")
        return
    if "completion" not in caps:
        print(
            f"\n⚠ '{name}' no aparece como modelo de chat/completion en Ollama "
            "(¿modelo de embeddings o de otro tipo?). Puede que no funcione como asistente conversacional."
        )
    if "tools" not in caps:
        print(
            f"\n⚠ '{name}' no tiene la capacidad 'tools' en Ollama: la búsqueda web "
            "(web_search) y los lugares cercanos (find_nearby_places) probablemente NO "
            "funcionen bien con este modelo — puede que las describa en texto en vez de "
            "usarlas, o que las ignore por completo."
        )


def update_base_model_in_file(name: str, new_base_model: str):
    """Reemplaza SOLO la línea 'base_model:' dentro de la sección `name` de
    assistants.yaml, dejando todo lo demás (comentarios, personality,
    otros asistentes) exactamente igual — no se hace un round-trip
    completo del YAML porque eso perdería los comentarios del archivo."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        text = f.read()

    section_re = re.compile(rf"(?m)^{re.escape(name)}:\s*$")
    m = section_re.search(text)
    if not m:
        print(f"No encontré la sección '{name}:' en assistants.yaml.")
        sys.exit(1)

    start = m.end()
    next_section = re.search(r"(?m)^\S", text[start:])
    end = start + next_section.start() if next_section else len(text)
    section_text = text[start:end]

    new_section_text, n = _BASE_MODEL_LINE_RE.subn(rf'\g<1>"{new_base_model}"', section_text, count=1)
    if n == 0:
        print(f"No encontré 'base_model:' dentro de la sección '{name}:'.")
        sys.exit(1)

    new_text = text[:start] + new_section_text + text[end:]

    backup_path = CONFIG_PATH + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"assistants.yaml actualizado (respaldo en '{os.path.basename(backup_path)}').")


def smoke_test(name: str):
    print(f"\nProbando '{name}'...")
    try:
        from app.core.assistant_engine import ask
        reply = ask(name, [{"role": "user", "content": "Responde solo con la palabra: listo"}])
        print(f"{name}> {reply}")
    except Exception as e:
        print(f"No se pudo probar '{name}' automáticamente ({e}). Revísalo a mano con run_{name}.bat si existe.")


def main():
    print("=== Cambiar el modelo de IA base de un asistente ===\n")
    assistants = list_assistants()
    if not assistants:
        print("No hay ningún asistente definido en assistants.yaml.")
        sys.exit(1)

    print("Asistentes disponibles:")
    for i, name in enumerate(assistants, start=1):
        print(f"  {i}) {name}  (modelo actual: {current_base_model(name)})")
    choice = input(f"Elige uno [1-{len(assistants)}]: ").strip()
    try:
        name = assistants[int(choice) - 1]
    except (ValueError, IndexError):
        print("Opción no válida.")
        sys.exit(1)

    try:
        installed = ollama_installed_models()
    except requests.exceptions.RequestException:
        print("No puedo conectar con Ollama. ¿Está corriendo ('ollama serve' o la app de Ollama)?")
        sys.exit(1)

    print("\nModelos ya instalados en Ollama:")
    for m in sorted(installed):
        print(f"  - {m}")

    new_base_model = input(
        "\nNombre del modelo a usar (tal como en 'ollama list' o en https://ollama.com/library, "
        "p. ej. qwen3.6:35b, llama3.1:8b): "
    ).strip()
    if not new_base_model:
        print("No escribiste nada, cancelado.")
        sys.exit(1)

    if not model_is_installed(new_base_model, installed):
        confirm = input(f"'{new_base_model}' no está instalado. ¿Descargarlo ahora? [s/N]: ").strip().lower()
        if confirm != "s":
            print("Cancelado.")
            sys.exit(0)
        pull_model(new_base_model)

    warn_capabilities(new_base_model)
    update_base_model_in_file(name, new_base_model)
    smoke_test(name)

    print(f"\nListo. '{name}' ahora usa '{new_base_model}'.")
    print("No hace falta tocar nada más: voice_loop.py y assistant_engine.py leen")
    print("assistants.yaml en cada arranque. Si las respuestas se sienten raras")
    print("(muy planas/muy erráticas), ajusta temperature/top_k/top_p a mano ahí mismo.")


if __name__ == "__main__":
    main()
