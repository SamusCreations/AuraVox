r"""
Switches the base AI (LLM) model behind any assistant defined in
config/assistants.yaml.

Downloads the new model if needed ("ollama pull"), updates the "base_model"
field of the selected assistant in assistants.yaml (only that line — comments
and the rest of the configuration remain untouched), and runs a quick smoke
test.

Run: extras\switch_model.bat (or "python app/scripts/switch_model.py").
Requires Ollama to be running.
"""
import os
import re
import subprocess
import sys

import requests
import yaml

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
    return [name for name in _read_raw_config() if name not in NON_ASSISTANT_KEYS]


def current_base_model(name: str) -> str:
    return (_read_raw_config().get(name) or {}).get("base_model", "?")


def pull_model(name: str):
    print(f"\nDownloading '{name}' from Ollama (this may take a while depending on size)...\n")
    result = subprocess.run(["ollama", "pull", name])
    if result.returncode != 0:
        print(
            f"\nCould not download '{name}'. Make sure the model name is exact "
            "(as shown in 'ollama list' or at https://ollama.com/library) and try again."
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
        print(f"\n(Could not read capabilities for '{name}' from Ollama; continuing anyway.)")
        return
    if "completion" not in caps:
        print(
            f"\n⚠ '{name}' does not appear as a chat/completion model in Ollama "
            "(is it an embedding model?). It may not work as a conversational assistant."
        )
    if "tools" not in caps:
        print(
            f"\n⚠ '{name}' does not report the 'tools' capability in Ollama: web search "
            "(web_search) and nearby places (find_nearby_places) will likely NOT work "
            "properly with this model."
        )


def update_base_model_in_file(name: str, new_base_model: str):
    """Replaces ONLY the 'base_model:' line inside section `name` of
    assistants.yaml, leaving comments and all other assistants untouched."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        text = f.read()

    section_re = re.compile(rf"(?m)^{re.escape(name)}:\s*$")
    m = section_re.search(text)
    if not m:
        print(f"Could not find section '{name}:' in assistants.yaml.")
        sys.exit(1)

    start = m.end()
    next_section = re.search(r"(?m)^\S", text[start:])
    end = start + next_section.start() if next_section else len(text)
    section_text = text[start:end]

    new_section_text, n = _BASE_MODEL_LINE_RE.subn(rf'\g<1>"{new_base_model}"', section_text, count=1)
    if n == 0:
        print(f"Could not find 'base_model:' inside section '{name}:'.")
        sys.exit(1)

    new_text = text[:start] + new_section_text + text[end:]

    backup_path = CONFIG_PATH + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"assistants.yaml updated (backup saved to '{os.path.basename(backup_path)}').")


def smoke_test(name: str):
    print(f"\nTesting '{name}'...")
    try:
        from app.core.assistant_engine import ask
        reply = ask(name, [{"role": "user", "content": "Reply with only the word: ready"}])
        print(f"{name}> {reply}")
    except Exception as e:
        print(f"Could not test '{name}' automatically ({e}). You can test it manually with extras\\run_assistant.bat {name}.")


def main():
    print("=== Switch an Assistant's Base AI Model ===\n")
    assistants = list_assistants()
    if not assistants:
        print("No assistants are defined in assistants.yaml.")
        sys.exit(1)

    print("Available assistants:")
    for i, name in enumerate(assistants, start=1):
        print(f"  {i}) {name}  (current model: {current_base_model(name)})")
    choice = input(f"Choose one [1-{len(assistants)}]: ").strip()
    try:
        name = assistants[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid option.")
        sys.exit(1)

    try:
        installed = ollama_installed_models()
    except requests.exceptions.RequestException:
        print("Cannot connect to Ollama. Is it running ('ollama serve' or the Ollama app)?")
        sys.exit(1)

    print("\nModels currently installed in Ollama:")
    for m in sorted(installed):
        print(f"  - {m}")

    new_base_model = input(
        "\nModel name to use (as shown in 'ollama list' or https://ollama.com/library, "
        "e.g. qwen3:14b, llama3.1:8b): "
    ).strip()
    if not new_base_model:
        print("No model name entered. Cancelled.")
        sys.exit(1)

    if not model_is_installed(new_base_model, installed):
        confirm = input(f"'{new_base_model}' is not installed. Download it now? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes", "s", "si"):
            print("Cancelled.")
            sys.exit(0)
        pull_model(new_base_model)

    warn_capabilities(new_base_model)
    update_base_model_in_file(name, new_base_model)
    smoke_test(name)

    print(f"\nDone! '{name}' now uses '{new_base_model}'.")
    print("No further steps needed: voice_loop.py and assistant_engine.py read")
    print("assistants.yaml on every startup. If replies feel too flat or erratic,")
    print("you can tune temperature/top_k/top_p in assistants.yaml or the Web UI.")


if __name__ == "__main__":
    main()
