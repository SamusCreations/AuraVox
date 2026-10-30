"""
Escucha manos libres de la interfaz web: el "voice loop" corriendo DENTRO
del servidor de AuraVox.bat, para llamar a cualquier asistente por su
nombre (o con su tecla de push to talk) sin tocar la página.

Reparto del trabajo:
- AQUÍ (servidor): el micrófono (abierto de forma continua, mic_stream.py),
  Whisper, reconocer el nombre de quien tenga `wake_word` activo (con sus
  variantes de wake_words.txt), la tecla de push to talk y cuándo se abre y
  se cierra la conversación.
- EN LA PÁGINA (app.js): todo lo demás, igual que la conversación por voz de
  siempre — abrir al asistente que llamaste con su aura, la conversación
  grupal (invitados, rondas, a quién se le habló), el modelo y la voz.
  Invitar o sacar asistentes ("Jarvis, invita a Bella") lo entiende el
  propio modelo: son herramientas suyas (ver chat_runtime.group_tools), no
  palabras clave.
La página recibe lo que pasa con /api/voice/events (long polling) y avisa
qué está haciendo (pensando, hablando) con /api/voice/client.

Mientras el asistente piensa o habla, solo cuenta lo que empiece con un
nombre (o una tecla de push to talk): así su propia voz por el altavoz no se
toma como una pregunta, igual que el barge-in de voice_loop.py.

Si hay varias pestañas abiertas, responde una sola: la última que se usó
("controladora", ver claim()). Sin ninguna página abierta, o con el
micrófono silenciado desde la interfaz, el micrófono se cierra.

Mientras la página tiene abierta la conversación por voz, la escucha se
PAUSA (set_paused) y el micrófono del servidor se cierra: la conversación
usa el micrófono del navegador (con cancelación de eco) y quién responde lo
decide la página. Al terminar la conversación, la escucha vuelve sola.
"""
import collections
import json
import os
import threading
import time
import traceback

from app import paths
from app.core.assistant_common import load_assistants_config, pipeline_languages
from app.voice import push_to_talk as ptt
from app.voice import wake_word_utils as ww
from app.voice.mic_stream import Interrupted, MicStream
from app.voice.stt_whisper import CONFIG as STT_CONFIG
from app.webui import chat_runtime
from app.webui.server_log import log

# Si el micrófono quedó silenciado desde la interfaz (sigue así al reabrirla).
SETTINGS_PATH = os.path.join(paths.CONFIG_DIR, "voice_listener.json")

# ══════════════════════════════════════════════════════════════════════
# PLANTILLA DE PARÁMETROS — edita estos valores cuando quieras
# ══════════════════════════════════════════════════════════════════════
CONFIG = {
    # Segundos de silencio, después de que el asistente terminó de hablar,
    # antes de cerrar la conversación y volver a exigir su nombre.
    # (Empezando la conversación desde el botón de la página, no se cierra
    # sola: hay que terminarla con el botón o diciendo que salga.)
    "session_timeout": 8.0,
    # Lo mismo para un asistente que solo se llama con su tecla (sin
    # `wake_word`): no deja la conversación abierta, cada turno es con la
    # tecla. Este margen solo cubre lo que tarda la página en avisar que
    # empezó a pensar.
    "ptt_session_timeout": 1.5,
    # Una página que no consulta en este tiempo se da por cerrada.
    "client_timeout": 35.0,
    # Tope de espera de cada consulta de la página (long polling).
    "poll_timeout": 20.0,
    # Pitido al decir solo el nombre ("Jarvis" … pitido … "qué hora es").
    "ack_beep": (880, 150),
    # Cada cuánto se revisa el estado (silenciado, página abierta...) mientras no se habla.
    "listen_poll": 0.4,
    "wake_word_ratio": ww.DEFAULT_RATIO,
}
# ══════════════════════════════════════════════════════════════════════

_LOG = "hands-free"


def _short(text: str, n: int = 70) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


class VoiceListener:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cond = threading.Condition()
        self._events = collections.deque(maxlen=300)
        self._last_id = 0
        self._muted = self._load_muted()
        self._status = "off"
        self._error = ""
        self._controller = None
        self._seen = {}
        # Lo que avisa la página controladora: si está pensando/hablando,
        # los idiomas y el idioma de la conversación abierta y la pausa
        # para pensar que eligió.
        self._client = {"busy": None, "langs": [], "hint": None, "pause_ms": None}
        # Conversación abierta: {"assistant", "timeout" (None = no se cierra sola), "last"}.
        self._session = None
        self._last_lang = {}
        self._mic = MicStream(STT_CONFIG)
        # Página que pausó la escucha (tiene abierta su conversación por voz).
        self._paused_by = None
        self._config_lock = threading.Lock()
        self._stt_ready = False
        self._config_key = None
        self._assistants = {}
        self._names_all = {}
        self._names_wake = {}
        self._exclusions = set()
        self._display = {}
        self._stop = threading.Event()
        self._thread = None

    # ── Ajustes guardados ──────────────────────────────────────────────
    @staticmethod
    def _load_muted() -> bool:
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                return bool(json.load(f).get("muted"))
        except (OSError, ValueError, AttributeError):
            return False

    @staticmethod
    def _save_muted(muted: bool) -> None:
        tmp = SETTINGS_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"muted": muted}, f)
            os.replace(tmp, SETTINGS_PATH)
        except OSError as e:
            log(_LOG, f"could not save microphone mute state ({e})", "warn")

    # ── Ciclo de vida ──────────────────────────────────────────────────
    def start(self) -> None:
        if not self.enabled:
            self._status = "disabled"
            return
        self._thread = threading.Thread(target=self._run, name="voice-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=3)
        self._mic.close()

    # ── API para el servidor HTTP ──────────────────────────────────────
    def _alive(self, client) -> bool:
        return client is not None and time.monotonic() - self._seen.get(client, -1e9) < CONFIG["client_timeout"]

    def _touch(self, client: str) -> None:
        self._seen[client] = time.monotonic()
        if not self._alive(self._controller):
            self._controller = client

    def _state_locked(self) -> dict:
        s = self._session
        return {
            "enabled": self.enabled,
            "muted": self._muted,
            "status": self._status,
            "error": self._error,
            "controller": self._controller,
            "session": s["assistant"] if s else None,
            "manual": bool(s and s["timeout"] is None),
            "paused": self._paused_locked(),
        }

    def _paused_locked(self) -> bool:
        # Si la página que pausó se cerró sin avisar, la escucha vuelve sola.
        return self._paused_by is not None and self._alive(self._paused_by)

    def state(self) -> dict:
        with self._cond:
            return self._state_locked()

    def poll(self, client: str, after: int, wait: float) -> dict:
        """Eventos nuevos (id > `after`) para la página `client`; si no hay,
        espera hasta `wait` segundos a que haya alguno."""
        deadline = time.monotonic() + max(0.0, min(wait, CONFIG["poll_timeout"]))
        with self._cond:
            self._touch(client)
            self._cond.notify_all()  # el hilo de escucha puede estar esperando una página
            if after > self._last_id:
                after = 0  # el servidor se reinició: la página tenía otra numeración
            while not self._stop.is_set():
                events = [e for e in self._events if e["id"] > after]
                remaining = deadline - time.monotonic()
                if events or remaining <= 0:
                    break
                self._cond.wait(remaining)
            self._touch(client)
            return {"events": events, "last": self._last_id, "state": self._state_locked()}

    def claim(self, client: str) -> dict:
        """La pestaña que se está usando pasa a ser la que responde."""
        with self._cond:
            self._seen[client] = time.monotonic()
            if self._controller != client:
                self._controller = client
                self._emit_locked("state")
            return self._state_locked()

    def set_muted(self, muted: bool) -> dict:
        with self._cond:
            if muted != self._muted:
                self._muted = muted
                if muted:
                    self._end_session_locked("muted")
                self._emit_locked("state")
                self._cond.notify_all()
        self._save_muted(muted)
        log(_LOG, "microphone muted from Web UI" if muted else "microphone unmuted from Web UI")
        return self.state()

    def set_paused(self, client: str, paused: bool) -> dict:
        """La página entra (True) o sale (False) de su conversación por voz,
        que usa el micrófono del navegador."""
        with self._cond:
            self._seen[client] = time.monotonic()
            was = self._paused_locked()
            if paused:
                self._paused_by = client
                self._end_session_locked("paused")
            elif self._paused_by == client:
                self._paused_by = None
            if was != self._paused_locked():
                self._emit_locked("state")
            self._cond.notify_all()
        log(_LOG, "paused: Web UI is in voice mode (using browser microphone)" if paused
            else "Web UI exited voice mode: resuming PC microphone listening")
        return self.state()

    def canonicalize(self, text: str) -> str:
        """`text` con los nombres de los asistentes bien escritos ("Harvis"
        → "Jarvis"), para lo que transcribe el micrófono del navegador."""
        if not text:
            return text
        self._reload_config()
        return ww.canonicalize(text, self._names_all, self._exclusions, self._display, CONFIG["wake_word_ratio"])

    def report(self, client: str, data: dict) -> None:
        """Lo que está haciendo la página: `busy` ("thinking" | "speaking" |
        None), `langs` e `hint` (idiomas de la conversación abierta) y
        `pause_ms` (pausa para pensar)."""
        busy = data.get("busy") if data.get("busy") in ("thinking", "speaking") else None
        langs = [c for c in data.get("langs") or [] if c in self._pipeline()]
        hint = data.get("hint") if data.get("hint") in self._pipeline() else None
        try:
            pause_ms = min(10000, max(500, int(data.get("pause_ms")))) if data.get("pause_ms") else None
        except (TypeError, ValueError):
            pause_ms = None
        with self._cond:
            self._seen[client] = time.monotonic()
            if client != self._controller:
                return
            was_busy = self._client["busy"]
            self._client.update(busy=busy, langs=langs, hint=hint, pause_ms=pause_ms)
            if self._session and (busy or was_busy):
                self._session["last"] = time.monotonic()  # el silencio se cuenta desde que terminó de hablar

    def open_session(self, client: str, assistant: str = None) -> dict:
        """Conversación abierta desde el botón de la página: no se cierra
        sola por silencio."""
        with self._cond:
            self._seen[client] = time.monotonic()
            self._controller = client
            self._session = {"assistant": assistant, "timeout": None, "last": time.monotonic()}
            self._emit_locked("state")
            self._cond.notify_all()
            return self._state_locked()

    def close_session(self, client: str) -> dict:
        with self._cond:
            if client == self._controller:
                self._end_session_locked(None)
            return self._state_locked()

    # ── Eventos ────────────────────────────────────────────────────────
    def _emit_locked(self, kind: str, **data) -> None:
        self._last_id += 1
        self._events.append({"id": self._last_id, "type": kind, "controller": self._controller, **data})
        self._cond.notify_all()

    def _emit(self, kind: str, **data) -> None:
        with self._cond:
            self._emit_locked(kind, **data)

    def _set_status(self, status: str, error: str = "") -> None:
        with self._cond:
            if status != self._status or error != self._error:
                self._status, self._error = status, error
                self._emit_locked("state")

    def _end_session_locked(self, reason) -> None:
        if self._session:
            assistant = self._session["assistant"]
            self._session = None
            self._emit_locked("session_end", assistant=assistant, reason=reason)

    def _open_session_locked(self, assistant: str, auto_close: bool = True) -> None:
        if self._session:
            self._session["last"] = time.monotonic()
            return
        self._session = {
            "assistant": assistant,
            "timeout": CONFIG["session_timeout"] if auto_close else CONFIG["ptt_session_timeout"],
            "last": time.monotonic(),
        }

    # ── Configuración de los asistentes ────────────────────────────────
    _pipeline_cache = None

    def _pipeline(self) -> list:
        if VoiceListener._pipeline_cache is None:
            VoiceListener._pipeline_cache = pipeline_languages()
        return VoiceListener._pipeline_cache

    def _reload_config(self) -> None:
        """Relee assistants.yaml y wake_words.txt si cambiaron (se editan
        desde la misma interfaz mientras la escucha sigue)."""
        with self._config_lock:
            self._reload_config_locked()

    def _reload_config_locked(self) -> None:
        try:
            key = tuple(os.path.getmtime(p) for p in (paths.ASSISTANTS_YAML, paths.WAKE_WORDS_TXT)
                        if os.path.exists(p))
        except OSError:
            return
        if key == self._config_key:
            return
        try:
            configs = load_assistants_config(paths.ASSISTANTS_YAML)
        except Exception as e:  # noqa: BLE001 — un error al editar a mano no debe tumbar la escucha
            log(_LOG, f"could not read assistants.yaml ({e}); keeping previous configuration", "warn")
            self._config_key = key
            return
        aliases, exclusions = ww.load_wake_words()
        pipeline = set(self._pipeline())
        assistants = {}
        for name, cfg in configs.items():
            assistants[name] = {
                "label": cfg["label"],
                "wake_word": cfg["wake_word"],
                "ptt_key": cfg["push_to_talk_key"],
                "language": cfg["language"],
                "languages": (set(cfg["languages"]) & pipeline) or pipeline,
            }
        self._assistants = assistants
        self._names_all = {name: {ww.normalize(name)} | aliases.get(name, set()) for name in assistants}
        self._names_wake = {name: names for name, names in self._names_all.items() if assistants[name]["wake_word"]}
        self._exclusions = exclusions
        self._display = {name: a["label"].title() for name, a in assistants.items()}
        self._config_key = key
        ways = [n.title() for n in self._names_wake] + [f"{a['ptt_key']} ({n.title()})" for n, a in assistants.items() if a["ptt_key"]]
        log(_LOG, f"wake triggers: {', '.join(ways) or '(no assistant has voice activation enabled)'}")

    def _hint_for(self, name: str) -> str:
        a = self._assistants.get(name) or {}
        return self._last_lang.get(name) or a.get("language")

    # ── Bucle de escucha ───────────────────────────────────────────────
    def _should_listen(self) -> bool:
        with self._cond:
            return (self.enabled and not self._muted and self._alive(self._controller)
                    and not self._paused_locked())

    def _go_idle(self) -> None:
        with self._cond:
            alive = self._alive(self._controller)
            if not alive:
                self._end_session_locked("no_page")
            status = "muted" if self._muted else "paused" if self._paused_locked() else "idle"
        if self._mic.is_open:
            self._mic.close()
            why = {"muted": "muted", "paused": "browser is using microphone"}.get(status, "no browser tab open")
            log(_LOG, f"microphone closed ({why})")
        self._set_status(status)

    def _ensure_ready(self) -> bool:
        if not self._mic.is_open:
            self._set_status("loading")
            try:
                self._mic.open()
            except Exception as e:  # noqa: BLE001 — sin micrófono, sin dispositivo de entrada, etc.
                self._set_status("error", str(e))
                log(_LOG, f"could not open microphone: {e}", "warn")
                self._stop.wait(5)
                return False
            log(_LOG, "microphone open, listening")
        if not self._stt_ready:
            self._set_status("loading")
            chat_runtime.load_stt()
            self._stt_ready = True
        self._reload_config()
        return True

    def _busy(self):
        with self._cond:
            return self._client["busy"]

    def _interrupt(self):
        if not self._should_listen():
            return "@stop"
        for name, a in self._assistants.items():
            if a["ptt_key"] and ptt.is_pressed(a["ptt_key"]):
                return name
        return None

    def _silence_timeout(self):
        with self._cond:
            pause = self._client["pause_ms"] if self._session else None
        return pause / 1000 if pause else None

    def _expire_session(self) -> None:
        with self._cond:
            s = self._session
            if not s or s["timeout"] is None or self._client["busy"]:
                return
            if time.monotonic() - s["last"] > s["timeout"]:
                label = (self._assistants.get(s["assistant"]) or {}).get("label", s["assistant"])
                self._end_session_locked("silence")
                log(_LOG, f"conversation with {label} closed due to silence; call by name again")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if not self._should_listen():
                    self._go_idle()
                    with self._cond:
                        self._cond.wait(0.5)
                    continue
                if not self._ensure_ready():
                    continue
                if self._status not in ("listening", "hearing", "transcribing"):
                    self._set_status("listening")
                self._expire_session()
                # Mientras habla la página, su voz por el altavoz no es ruido ambiente.
                self._mic.freeze_noise(self._busy() == "speaking")
                audio = self._mic.listen(
                    timeout=CONFIG["listen_poll"],
                    interrupt=self._interrupt,
                    silence_timeout=self._silence_timeout(),
                    on_start=lambda: self._set_status("hearing"),
                )
                if isinstance(audio, Interrupted):
                    if audio.value != "@stop":
                        self._ptt_turn(audio.value)
                    continue
                if audio is None:
                    if self._status != "listening":
                        self._set_status("listening")
                    continue
                self._handle_audio(audio)
            except Exception as e:  # noqa: BLE001 — la escucha no debe morir por un error puntual
                traceback.print_exc()
                self._set_status("error", str(e))
                self._mic.close()
                self._stop.wait(3)
        self._mic.close()

    def _turn_languages(self):
        """(idiomas, pista) para transcribir: los de la conversación abierta
        (los avisa la página) o, sin conversación, todos los de los
        asistentes que se pueden llamar (todavía no se sabe a quién)."""
        with self._cond:
            if self._session and self._client["langs"]:
                return list(self._client["langs"]), self._client["hint"]
        union = set()
        for a in self._assistants.values():
            if a["wake_word"] or a["ptt_key"]:
                union |= a["languages"]
        return sorted(union or self._pipeline()), None

    def _handle_audio(self, audio) -> None:
        self._set_status("transcribing")
        langs, hint = self._turn_languages()
        text, lang, confident = chat_runtime.transcribe_array(audio, langs, hint, source=_LOG)
        if not text:
            self._set_status("listening")
            return
        ratio = CONFIG["wake_word_ratio"]
        wake, _rest = ww.find_wake_word(text, self._names_wake, self._exclusions, ratio)
        with self._cond:
            in_session = self._session is not None
        if wake and not in_session and not confident:
            # Detección de idioma dudosa: se repite con la pista y los
            # idiomas del asistente que llamaron (ver voice_loop._transcribe_addressed).
            a = self._assistants[wake]
            if lang != self._hint_for(wake) or lang not in a["languages"]:
                text2, lang2, _ = chat_runtime.transcribe_array(audio, sorted(a["languages"]), self._hint_for(wake), source=_LOG)
                wake2, _rest2 = ww.find_wake_word(text2, self._names_wake, self._exclusions, ratio)
                if wake2 == wake:
                    text, lang = text2, lang2
        text = ww.canonicalize(text, self._names_all, self._exclusions, self._display, ratio)
        wake, remainder = ww.find_wake_word(text, self._names_wake, self._exclusions, ratio)
        self._route(text, lang, wake, remainder or "")
        self._set_status("listening")

    def _route(self, text: str, lang: str, wake, remainder: str, ptt_name: str = None) -> None:
        if wake:
            self._last_lang[wake] = lang
        with self._cond:
            busy = self._client["busy"]
            session = self._session
            payload = {"text": text, "lang": lang}
            if busy and not (wake or ptt_name):
                note = f"ignored while {'thinking' if busy == 'thinking' else 'speaking'} (does not start with wake word)"
            elif wake or ptt_name:
                name = ptt_name or wake
                if session:
                    session["last"] = time.monotonic()
                else:
                    self._open_session_locked(name, auto_close=self._can_follow_up(name))
                self._emit_locked("wake", **payload, assistant=name, remainder=remainder,
                                  ptt=bool(ptt_name), barge=bool(busy))
                note = f"called {name}" + (" (barge-in)" if busy else "")
            elif session:
                session["last"] = time.monotonic()
                self._emit_locked("utterance", **payload)
                note = "conversation follow-up turn"
            else:
                note = "ignored (does not start with any assistant's wake word)"
        log(_LOG, f"«{_short(text)}» [{lang}] → {note}")
        if wake and not remainder and not ptt_name:
            self._beep()

    def _can_follow_up(self, name: str) -> bool:
        """Un asistente que solo se llama con su tecla (sin `wake_word`) no
        deja la conversación abierta: cada turno es apretándola otra vez."""
        return bool((self._assistants.get(name) or {}).get("wake_word", True))

    def _beep(self) -> None:
        try:
            import winsound

            winsound.Beep(*CONFIG["ack_beep"])
        except (ImportError, RuntimeError):
            pass
        self._mic.flush()  # que el propio pitido no cuente como lo siguiente que se dice

    def _ptt_turn(self, name: str) -> None:
        a = self._assistants.get(name)
        if not a:
            return
        key = a["ptt_key"]
        self._set_status("hearing")
        log(_LOG, f"push-to-talk for {a['label']} [{key}]: listening while held down")
        audio = ptt.record_while_pressed(key, self._mic)
        ptt.wait_until_released(key)
        if audio is None:
            self._set_status("listening")
            return
        self._set_status("transcribing")
        text, lang, _ = chat_runtime.transcribe_array(audio, sorted(a["languages"]), self._hint_for(name), source=_LOG)
        if not text:
            self._set_status("listening")
            return
        ratio = CONFIG["wake_word_ratio"]
        text = ww.canonicalize(text, self._names_all, self._exclusions, self._display, ratio)
        self._last_lang[name] = lang
        self._route(text, lang, None, text, ptt_name=name)
        self._set_status("listening")
