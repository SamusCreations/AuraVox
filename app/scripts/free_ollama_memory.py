"""
Libera de inmediato TODOS los modelos que Ollama tenga cargados en memoria
(RAM/VRAM) en este momento, sin tener que cerrar y volver a abrir Ollama.

Por qué hace falta: mientras un asistente está corriendo, cada petición
pide keep_alive largo (ver assistant_common.py) para no recargar el modelo
entre turnos — eso solo se libera cuando el script termina normal (cierre
limpio, Ctrl+C). Si el proceso muere de otra forma (se cierra la ventana a
la fuerza, un crash, doble Ctrl+C encima de la limpieza) esa liberación
normal nunca llega a correr, y el modelo se queda cargado. Este script es
el botón de emergencia para esos casos: no importa qué lo dejó cargado,
libera todo lo que Ollama reporte en /api/ps ahora mismo.

Ejecutar: free_ollama_memory.bat (o "python free_ollama_memory.py").
Requiere que Ollama esté corriendo.
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
        print(f"  no se pudo liberar '{model_name}': {e}")
        return False


def main():
    print("Revisando qué modelos tiene Ollama cargados en memoria...\n")
    try:
        models = loaded_models()
    except requests.exceptions.RequestException as e:
        print(f"No pude conectar con Ollama ({e}). ¿Está corriendo ('ollama serve' o la app)?")
        sys.exit(1)

    if not models:
        print("Ningún modelo cargado en este momento — no hay nada que liberar.")
        return

    print("Modelos cargados ahora mismo:")
    for m in models:
        size_gb = (m.get("size_vram") or m.get("size") or 0) / (1024 ** 3)
        print(f"  - {m['name']} (~{size_gb:.1f} GB)")

    print()
    for m in models:
        print(f"Liberando '{m['name']}'...")
        unload(m["name"])

    time.sleep(1)  # dar un segundo a que Ollama procese los unloads antes de reconfirmar
    try:
        remaining = loaded_models()
    except requests.exceptions.RequestException:
        remaining = None

    if remaining is None:
        print("\nSe mandaron las órdenes de liberar (no pude reconfirmar el estado final con Ollama).")
    elif not remaining:
        print("\nListo — Ollama no tiene ningún modelo cargado en memoria ahora.")
    else:
        print(f"\nAviso: siguen cargados: {', '.join(m['name'] for m in remaining)} (puede que estén en uso ahora mismo).")


if __name__ == "__main__":
    main()
