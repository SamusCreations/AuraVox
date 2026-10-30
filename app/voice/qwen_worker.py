"""
Proceso aparte para las voces clonadas con Qwen3-TTS (modelo "Base").

Corre con OTRO Python, uno que tenga torch con CUDA (por defecto el de
ComfyUI-Easy-Install, ver voice_settings.default_qwen_python): el Python
portable de esta carpeta no trae torch y agregárselo serían ~5 GB más. El
paquete qwen_tts en sí va copiado en app/vendor.

Lo lanza y le habla app/voice/qwen_tts.py. Protocolo: una línea JSON por
petición en stdin y una por respuesta en stdout:

    {"op": "load", "model_dir": ..., "compile": true, "warmup_voice": {...}}
    {"op": "synth", "model_dir": ..., "text": ..., "language": "Spanish",
     "voice": {"id", "path", "ref_text", "stamp"}, "out": "salida.wav"}
    {"op": "unload"} | {"op": "quit"}

La "huella" de cada voz (create_voice_clone_prompt: tokens del audio de
referencia + embedding del hablante) se calcula una sola vez por voz y se
reutiliza en cada frase.

Velocidad: sin más, generaba a RTF ~3,5 (12 s para 3,5 s de audio) con la
GPU al 10-40 %: el modelo hace cientos de pasadas chicas por segundo de
audio y Python no alcanza a alimentar la GPU. Con `compile` se pasan por
torch.compile el modelo principal y el que genera los códigos de cada
cuadro: medido, RTF ~1,2 (3 veces más rápido). La primera vez compila ~4
min (queda en la caché de torch, en disco) y cada arranque después tarda
~1,5 min en prepararse; por eso el proceso queda vivo y la app lo calienta
de antemano.
"""
import json
import os
import sys
import time
import traceback

# stdout es el canal de respuestas: todo lo que impriman las librerías va a
# stderr (la app lo muestra en su consola con el prefijo [qwen-tts]).
_OUT = sys.stdout
sys.stdout = sys.stderr

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "app", "vendor"))

import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from qwen_tts import Qwen3TTSModel  # noqa: E402

_state = {"model": None, "model_dir": None, "prompts": {}, "compiled": False}


def _reply(obj: dict) -> None:
    _OUT.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _OUT.flush()


def _load(model_dir: str, compile_model: bool = False, warmup_voice: dict = None) -> dict:
    if _state["model"] is not None and _state["model_dir"] == model_dir and _state["compiled"] == compile_model:
        return {"seconds": 0.0, "compiled": _state["compiled"]}
    _unload()
    cuda = torch.cuda.is_available()
    t0 = time.time()
    _state["model"] = Qwen3TTSModel.from_pretrained(
        model_dir,
        device_map="cuda:0" if cuda else "cpu",
        dtype=torch.bfloat16 if cuda else torch.float32,
        attn_implementation="sdpa",
    )
    _state["model_dir"] = model_dir
    compiled = False
    if compile_model and cuda:
        try:
            talker = _state["model"].model.talker
            talker.code_predictor.model = torch.compile(talker.code_predictor.model, dynamic=True)
            talker.model = torch.compile(talker.model, dynamic=True)
            if warmup_voice:
                # La compilación pasa en la primera generación: se hace ya,
                # no con la primera frase de verdad.
                _state["model"].generate_voice_clone(
                    text="Hola, esto es una prueba para preparar la voz.", language="Spanish",
                    voice_clone_prompt=_prompt(warmup_voice))
            compiled = True
        except Exception:  # noqa: BLE001 — sin compilar igual funciona (más lento)
            traceback.print_exc()
            print("(no se pudo compilar el modelo; sigo sin compilar)", file=sys.stderr)
    _state["compiled"] = compiled
    langs = getattr(_state["model"].model, "get_supported_languages", None)
    return {
        "seconds": round(time.time() - t0, 2),
        "device": "GPU" if cuda else "CPU",
        "compiled": compiled,
        "languages": sorted(langs()) if callable(langs) else [],
    }


def _unload() -> None:
    _state["model"] = None
    _state["model_dir"] = None
    _state["compiled"] = False
    _state["prompts"].clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _prompt(voice: dict):
    key = (voice["id"], voice.get("stamp"))
    if key not in _state["prompts"]:
        ref_text = voice.get("ref_text") or None
        _state["prompts"][key] = _state["model"].create_voice_clone_prompt(
            ref_audio=voice["path"],
            ref_text=ref_text,
            # Sin lo que se dice en el audio, solo el timbre (menos parecido).
            x_vector_only_mode=not ref_text,
        )
    return _state["prompts"][key]


def _synth(req: dict) -> dict:
    loaded = _load(req["model_dir"], bool(req.get("compile")), req.get("voice"))
    t0 = time.time()
    wavs, sr = _state["model"].generate_voice_clone(
        text=req["text"],
        language=req.get("language") or "Auto",
        voice_clone_prompt=_prompt(req["voice"]),
        max_new_tokens=int(req.get("max_new_tokens") or 1024),
    )
    seconds = time.time() - t0
    sf.write(req["out"], wavs[0], sr)
    return {"seconds": round(seconds, 2), "audio_seconds": round(len(wavs[0]) / sr, 2), "sr": sr,
            "load_seconds": loaded.get("seconds", 0.0)}


def main() -> None:
    _reply({"ok": True, "ready": True, "torch": torch.__version__, "cuda": torch.cuda.is_available()})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "quit":
                _reply({"ok": True})
                break
            if op == "unload":
                _unload()
                _reply({"ok": True})
            elif op == "load":
                _reply({"ok": True, **_load(req["model_dir"], bool(req.get("compile")), req.get("warmup_voice"))})
            elif op == "synth":
                _reply({"ok": True, **_synth(req)})
            else:
                _reply({"ok": False, "error": f"operación desconocida: {op}"})
        except Exception as e:  # noqa: BLE001 — el proceso sigue vivo para la próxima
            traceback.print_exc()
            _reply({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
