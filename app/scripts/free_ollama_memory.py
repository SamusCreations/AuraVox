"""
Immediately unloads ALL models currently loaded in Ollama memory (RAM/VRAM)
without having to close and restart Ollama.

Why this is useful: while an assistant is running, each request sets a long
keep_alive (see assistant_common.py) so the model does not reload between
turns — that memory is only released when the script exits cleanly (Ctrl+C).
If the process is killed forcefully (closing the window, a crash, or double
Ctrl+C during cleanup), that normal unload step never runs and the model stays
in VRAM. This script is the emergency release button: regardless of what left
models loaded, it unloads everything Ollama reports in /api/ps right now.

Run: extras\free_ollama_memory.bat (or "python app/scripts/free_ollama_memory.py").
Requires Ollama to be running.
"""
import sys
import time

import requests

OLLAMA_PS_URL = "http://127.0.0.1:11434/api/ps"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"


def loaded_models() -> list:
    r = requests.get(OLLAMA_PS_URL, timeout=10)
    r.raise_for_status()
    return r.json().get("models", [])


def unload(model_name: str) -> bool:
    try:
        r = requests.post(
            OLLAMA_CHAT_URL,
            json={"model": model_name, "messages": [], "keep_alive": 0},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"  could not unload '{model_name}': {e}")
        return False


def main():
    print("Checking which models Ollama currently has loaded in memory...\n")
    try:
        models = loaded_models()
    except requests.exceptions.RequestException as e:
        print(f"Could not connect to Ollama ({e}). Is it running ('ollama serve' or the Ollama app)?")
        sys.exit(1)

    if not models:
        print("No models are currently loaded — nothing to free.")
        return

    print("Currently loaded models:")
    for m in models:
        size_gb = (m.get("size_vram") or m.get("size") or 0) / (1024 ** 3)
        print(f"  - {m['name']} (~{size_gb:.1f} GB)")

    print()
    for m in models:
        print(f"Unloading '{m['name']}'...")
        unload(m["name"])

    time.sleep(1)  # give Ollama a second to process the unloads before re-checking
    try:
        remaining = loaded_models()
    except requests.exceptions.RequestException:
        remaining = None

    if remaining is None:
        print("\nUnload requests sent (could not re-verify final state with Ollama).")
    elif not remaining:
        print("\nDone — Ollama has no models loaded in memory now.")
    else:
        print(f"\nWarning: still loaded: {', '.join(m['name'] for m in remaining)} (they may be actively in use right now).")


if __name__ == "__main__":
    main()
