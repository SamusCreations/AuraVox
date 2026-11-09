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
referencia + embedding del hablante) se calcula una sola vez por voz, se
guarda en cache/qwen-tts/prompts/ y se reutiliza en cada frase. Si la voz
tiene `full_path` (un audio largo, ver voice_reference.py), el embedding es
el promedio sobre todo ese audio en vez de sobre los ~20 s de referencia.

Velocidad (RTX 4080 SUPER, 0.6B): sin más, 0,65× tiempo real con la GPU al
10-40 %: el modelo hace cientos de pasadas chicas por cuadro y Python no
alcanza a alimentar la GPU. Con `compile`, CUDA graphs (qwen_graph.py):
3,6× tiempo real y 0,6 s de preparación. Si la captura falla se usa
torch.compile (1,9×, pero tarda 1,5-4 min en prepararse).
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

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
# El paquete vendorizado va primero: en esta carpeta también hay un qwen_tts.py.
sys.path.insert(0, os.path.join(_ROOT, "app", "vendor"))
sys.path.append(_HERE)
_PROMPTS_DIR = os.path.join(_ROOT, "cache", "qwen-tts", "prompts")
_PROMPT_VERSION = 2  # sube si cambia cómo se calcula la huella

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from qwen_tts import Qwen3TTSModel  # noqa: E402
from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem  # noqa: E402

_state = {"model": None, "model_dir": None, "prompts": {}, "compiled": False, "accel": "none", "requested": False}


def _reply(obj: dict) -> None:
    _OUT.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _OUT.flush()


def _load(model_dir: str, compile_model: bool = False, warmup_voice: dict = None) -> dict:
    if _state["model"] is not None and _state["model_dir"] == model_dir and _state["requested"] == compile_model:
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
    compiled, accel = False, "none"
    if compile_model and cuda:
        accel = _accelerate()
        compiled = accel != "none"
        if compiled and warmup_voice:
            # Lo que se prepara en la primera generación se hace ya, no con
            # la primera frase de verdad.
            _state["model"].generate_voice_clone(
                text="Hola, esto es una prueba para preparar la voz.", language="Spanish",
                voice_clone_prompt=_prompt(warmup_voice))
    _state["compiled"] = compiled
    _state["accel"] = accel
    _state["requested"] = compile_model
    langs = getattr(_state["model"].model, "get_supported_languages", None)
    return {
        "seconds": round(time.time() - t0, 2),
        "device": "GPU" if cuda else "CPU",
        "compiled": compiled,
        "accel": accel,
        "languages": sorted(langs()) if callable(langs) else [],
    }


def _accelerate() -> str:
    """CUDA graphs; si no se puede, torch.compile; "none" si tampoco."""
    try:
        import qwen_graph

        qwen_graph.install(_state["model"])
        return "cuda_graph"
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("(could not capture CUDA graphs; trying torch.compile)", file=sys.stderr)
    try:
        talker = _state["model"].model.talker
        talker.code_predictor.model = torch.compile(talker.code_predictor.model, dynamic=True)
        talker.model = torch.compile(talker.model, dynamic=True)
        return "compile"
    except Exception:  # noqa: BLE001 — sin acelerar igual funciona (más lento)
        traceback.print_exc()
        print("(could not compile model; continuing without acceleration)", file=sys.stderr)
        return "none"


def _unload() -> None:
    _state["model"] = None
    _state["model_dir"] = None
    _state["compiled"] = False
    _state["accel"] = "none"
    _state["prompts"].clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _read_mono(path: str):
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    return (audio.mean(axis=1) if audio.ndim > 1 else audio), sr


def _mean_embedding(path: str):
    """Embedding del hablante promediado en tramos de 10 s de un audio largo."""
    model = _state["model"].model
    audio, sr = _read_mono(path)
    if sr != model.speaker_encoder_sample_rate:
        import librosa

        audio = librosa.resample(y=audio, orig_sr=sr, target_sr=model.speaker_encoder_sample_rate)
        sr = model.speaker_encoder_sample_rate
    window = 10 * sr
    starts = range(0, max(1, len(audio) - window // 2), window)
    embeddings = [model.extract_speaker_embedding(audio=audio[s:s + window], sr=sr) for s in list(starts)[:30]]
    return torch.stack(embeddings).mean(dim=0)


def _build_prompt(voice: dict) -> VoiceClonePromptItem:
    ref_text = voice.get("ref_text") or None
    audio, sr = _read_mono(voice["path"])
    if ref_text:
        # La referencia termina en silencio: si no, el primer sonido generado
        # se contagia de cómo terminó el audio.
        audio = np.concatenate([audio, np.zeros(int(0.5 * sr), dtype=np.float32)])
    item = _state["model"].create_voice_clone_prompt(
        ref_audio=(audio, sr),
        ref_text=ref_text,
        # Sin lo que se dice en el audio, solo el timbre (menos parecido).
        x_vector_only_mode=not ref_text,
    )[0]
    if voice.get("full_path") and os.path.isfile(voice["full_path"]):
        item.ref_spk_embedding = _mean_embedding(voice["full_path"])
    return item


def _prompt(voice: dict):
    key = (voice["id"], voice.get("stamp"))
    if key in _state["prompts"]:
        return _state["prompts"][key]
    model_name = os.path.basename(_state["model_dir"])
    path = os.path.join(_PROMPTS_DIR, f"{model_name}__{voice['id']}__{voice.get('stamp')}__v{_PROMPT_VERSION}.pt")
    item = None
    try:
        saved = torch.load(path, map_location="cpu", weights_only=True)
        device = _state["model"].device
        code = saved["ref_code"]
        item = VoiceClonePromptItem(
            ref_code=None if code is None else code.to(device), ref_spk_embedding=saved["ref_spk_embedding"].to(device),
            x_vector_only_mode=code is None, icl_mode=code is not None, ref_text=saved["ref_text"])
    except (OSError, KeyError, RuntimeError, ValueError):
        pass
    if item is None:
        item = _build_prompt(voice)
        try:
            os.makedirs(_PROMPTS_DIR, exist_ok=True)
            for name in os.listdir(_PROMPTS_DIR):  # versiones viejas de esta voz
                if name.startswith(f"{model_name}__{voice['id']}__"):
                    os.remove(os.path.join(_PROMPTS_DIR, name))
            tmp = path + ".tmp"
            torch.save({"ref_code": None if item.ref_code is None else item.ref_code.cpu(),
                        "ref_spk_embedding": item.ref_spk_embedding.cpu(), "ref_text": item.ref_text}, tmp)
            os.replace(tmp, path)
        except OSError:
            traceback.print_exc()
    _state["prompts"][key] = [item]
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
            "load_seconds": loaded.get("seconds", 0.0), "accel": _state["accel"]}


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
