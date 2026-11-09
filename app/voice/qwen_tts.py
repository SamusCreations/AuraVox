"""
Voces clonadas con Qwen3-TTS para cualquier asistente (voice: custom:<id>).

Qwen3-TTS necesita torch, que el Python portable de esta carpeta no trae: se
corre en un proceso aparte (qwen_worker.py) con el Python configurado en
config/voice_settings.yaml (por defecto el de ComfyUI). Este módulo lo
lanza la primera vez que hace falta, le pasa las frases y lo reinicia si se
cae.

Qwen3-TTS habla 10 idiomas (QWEN_LANGUAGES). En los otros 21 del pipeline
la voz clonada usa su voz de respaldo de Supertonic (`fallback_voice`).

Con `compile` (por defecto) se usan CUDA graphs (ver qwen_graph.py y
qwen_worker.py): unos segundos de preparación y ~3,6× tiempo real. Mientras
se prepara (warm_up_async, que la app lanza al arrancar si algún asistente
usa una voz clonada), las respuestas salen con la voz de respaldo en vez de
quedarse esperando; las muestras de la interfaz sí esperan.

    voice = CustomVoice("custom:mi_voz")
    voice.speak("Hola", "salida.wav", lang="es")
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

from app import paths
from app.core import voice_settings

# Código ISO 639-1 → nombre que espera Qwen3-TTS.
QWEN_LANGUAGES = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean", "de": "German",
    "fr": "French", "ru": "Russian", "pt": "Portuguese", "es": "Spanish", "it": "Italian",
}

_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qwen_worker.py")


def _say(text: str) -> None:
    print(f"[qwen-tts] {text}")


class WarmingUp(RuntimeError):
    """El modelo todavía se está preparando (compilando)."""


class QwenTTSEngine:
    """Un solo proceso de Qwen3-TTS por aplicación (ver engine())."""

    START_TIMEOUT = 120
    CALL_TIMEOUT = 240

    def __init__(self):
        self._proc = None
        self._lines = None
        self._lock = threading.Lock()
        self.device = ""
        self.languages = []
        self.ready = False
        self.warming = False

    # ── Configuración ──────────────────────────────────────────────────
    @staticmethod
    def python() -> str:
        return voice_settings.load()["qwen_tts"]["python"] or voice_settings.default_qwen_python()

    @staticmethod
    def model_dir() -> str:
        name = voice_settings.QWEN_MODELS[voice_settings.load()["qwen_tts"]["model"]]
        return os.path.join(paths.QWEN_TTS_MODELS_DIR, name)

    def status(self) -> dict:
        python, model_dir = self.python(), self.model_dir()
        problem = ""
        if not python or not os.path.isfile(python):
            problem = "no Python with torch found (configure it in Shared Settings → Voices)"
        elif not os.path.isfile(os.path.join(model_dir, "config.json")):
            problem = f"missing model {os.path.basename(model_dir)} in cache/qwen-tts"
        return {"available": not problem, "problem": problem, "python": python,
                "model": voice_settings.load()["qwen_tts"]["model"], "running": self._proc is not None,
                "device": self.device, "ready": self.ready, "warming": self.warming}

    # ── Proceso ────────────────────────────────────────────────────────
    def _start(self) -> None:
        st = self.status()
        if not st["available"]:
            raise RuntimeError(st["problem"])
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        _say(f"starting cloned-voice worker process with {st['python']}")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [st["python"], "-u", _WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=paths.ROOT, creationflags=flags,
        )
        self._lines = queue.Queue()
        proc = self._proc

        def read_out():
            for line in proc.stdout:
                self._lines.put(line)
            self._lines.put(None)

        def read_err():
            seen = set()
            for line in proc.stderr:
                line = line.rstrip()
                # transformers repite el mismo aviso decenas de veces por carga:
                # cada mensaje distinto se muestra una sola vez.
                if not line or "it/s]" in line or line in seen:
                    continue
                seen.add(line)
                _say(line)

        threading.Thread(target=read_out, daemon=True).start()
        threading.Thread(target=read_err, daemon=True).start()
        ready = self._read(self.START_TIMEOUT)
        if not ready.get("ok"):
            raise RuntimeError(f"Qwen3-TTS worker failed to start: {ready.get('error')}")
        _say(f"ready (torch {ready.get('torch')}, CUDA {'yes' if ready.get('cuda') else 'no'})")

    def _read(self, timeout: float) -> dict:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self._kill()
            raise RuntimeError("Qwen3-TTS did not respond in time")
        if line is None:
            self._kill()
            raise RuntimeError("Qwen3-TTS worker process exited (see console)")
        return json.loads(line)

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
        self.device = ""
        self.ready = False

    def _call(self, request: dict, timeout: float = None) -> dict:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                self._start()
            self._proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
            reply = self._read(timeout or self.CALL_TIMEOUT)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error") or "error de Qwen3-TTS")
        return reply

    # ── Uso ────────────────────────────────────────────────────────────
    @staticmethod
    def _voice_payload(voice: dict) -> dict:
        return {"id": voice["id"], "path": voice["path"], "full_path": voice.get("full_path") or "",
                "ref_text": voice["ref_text"], "stamp": voice["stamp"]}

    def load(self, warmup_voice: dict = None) -> dict:
        """Carga (y, con `compile`, compila y calienta) el modelo. Puede
        tardar minutos: para no bloquear, warm_up_async()."""
        compile_model = voice_settings.load()["qwen_tts"]["compile"]
        warmup_voice = warmup_voice or next(filter(None, map(voice_settings.get_voice,
                                                             [v["id"] for v in voice_settings.custom_voices()])), None)
        t0 = time.time()
        if compile_model:
            _say("preparing model (CUDA graphs)…")
        reply = self._call({"op": "load", "model_dir": self.model_dir(), "compile": compile_model,
                            "warmup_voice": self._voice_payload(warmup_voice) if warmup_voice else None}, timeout=900)
        if reply.get("device"):
            self.device = reply["device"]
            self.languages = reply.get("languages") or []
        self.ready = True
        _say(f"model {os.path.basename(self.model_dir())} ready in {time.time() - t0:.1f}s ({self.device}, "
             f"{reply.get('accel') or 'none'})")
        return reply

    def warm_up_async(self) -> bool:
        """Prepara el modelo en segundo plano (si se puede y no se está
        haciendo ya). True si lo empezó."""
        if self.ready or self.warming or not self.status()["available"] or not voice_settings.custom_voices():
            return False
        self.warming = True

        def run():
            try:
                self.load()
            except Exception as e:  # noqa: BLE001
                _say(f"could not warm up model: {e}")
            finally:
                self.warming = False

        threading.Thread(target=run, name="qwen-warmup", daemon=True).start()
        return True

    def synthesize(self, text: str, voice: dict, lang: str, out_path: str, wait: bool = False) -> dict:
        """Escribe en `out_path` `text` dicho con la voz clonada `voice`
        (como la devuelve voice_settings.get_voice). Si el modelo todavía no
        está listo: con `wait`, espera a que se prepare; si no, empieza a
        prepararlo en segundo plano y lanza WarmingUp (el que llama usa la
        voz de respaldo)."""
        if not self.ready:
            if not wait:
                self.warm_up_async()
                raise WarmingUp("cloned voice is warming up")
            if not self.warming:
                self.load(voice)
        reply = self._call({
            "op": "synth", "model_dir": self.model_dir(), "text": text,
            "language": QWEN_LANGUAGES.get(lang, "Auto"), "out": out_path,
            "compile": voice_settings.load()["qwen_tts"]["compile"], "voice": self._voice_payload(voice),
        }, timeout=900)
        speed = reply["audio_seconds"] / max(reply["seconds"], 0.01)
        _say(f"{voice['id']} [{lang}] on {self.device}: {reply['seconds']:.2f}s for {reply['audio_seconds']:.1f}s of "
             f"audio ({speed:.1f}x real time, {reply.get('accel') or 'none'})")
        return reply

    def release(self) -> bool:
        """Cierra el proceso (libera su VRAM). True si estaba corriendo."""
        with self._lock:
            if self._proc is None:
                return False
            try:
                self._proc.stdin.write(json.dumps({"op": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
            self._kill()
            return True


_engine = None
_engine_lock = threading.Lock()


def engine() -> QwenTTSEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = QwenTTSEngine()
        return _engine


def speaks(lang: str) -> bool:
    """¿Qwen3-TTS habla este idioma? (si no, se usa la voz de respaldo)."""
    return lang in QWEN_LANGUAGES


class CustomVoice:
    """Misma interfaz que supersonictts.JarvisVoice, con una voz clonada. En
    los idiomas que Qwen3-TTS no habla (o si no está disponible) usa la voz
    de respaldo de Supertonic de esa voz."""

    def __init__(self, code: str, config: dict):
        from app.voice.supersonictts import JarvisVoice

        self.code = code
        self.config = config
        voice = voice_settings.get_voice(code) or {}
        self._fallback = JarvisVoice({**config, "voice": voice.get("fallback_voice", "M5")})

    def _load(self):
        self._fallback._load()  # el respaldo siempre listo; Qwen se carga con la primera frase

    def release(self) -> None:
        self._fallback.release()

    def speak(self, text: str, out_path: str = "salida.wav", lang: str = None) -> str:
        lang = lang or self.config.get("language", "es")
        voice = voice_settings.get_voice(self.code)
        if voice and speaks(lang):
            try:
                engine().synthesize(text, voice, lang, out_path)
                return out_path
            except WarmingUp:
                print(f"(cloned voice {self.code} warming up; using fallback voice in the meantime)")
            except Exception as e:  # noqa: BLE001 — sin la voz clonada, que al menos hable
                print(f"(cloned voice {self.code} unavailable: {e}; using fallback voice)")
        return self._fallback.speak(text, out_path, lang=lang)


def make_voice(config: dict):
    """La voz de un asistente: Supertonic o clonada, según `config["voice"]`."""
    if voice_settings.is_custom(config.get("voice")):
        return CustomVoice(config["voice"], config)
    from app.voice.supersonictts import JarvisVoice

    return JarvisVoice(config)


if __name__ == "__main__":
    # Prueba: python -m app.voice.qwen_tts <id> "texto" [idioma]
    sys.path.insert(0, paths.ROOT)
    vid, text = sys.argv[1], sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else "es"
    v = voice_settings.get_voice(vid)
    print(engine().synthesize(text, v, lang, os.path.join(paths.AUDIO_DIR, f"qwen_{vid}.wav")))
    engine().release()
