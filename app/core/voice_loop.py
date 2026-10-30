"""
Bucle de voz estilo Alexa: escucha el micrófono en continuo, transcribe con
Whisper (stt_whisper.py) y, si la frase empieza por el nombre de alguno de
los asistentes definidos en assistants.yaml (con tolerancia a errores de
transcripción), le despacha el comando (assistant_engine.py) y reproduce la
respuesta con su voz (supersonictts.py).

Los asistentes NO están hardcodeados aquí: se leen de assistants.yaml al
arrancar. Agregar uno nuevo (o quitar uno) es cuestión de editar ese
archivo, no este script.

Ejecutar:
    python voice_loop.py
Requiere que Ollama esté corriendo (`ollama serve`).
"""
import gc
import os
import queue
import re
import sys
import threading
import time
import winsound

import requests
import numpy as np
import sounddevice as sd
import soundfile as sf

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collections import namedtuple

from app import paths
from app.voice.supersonictts import release_shared_tts
from app.voice.qwen_tts import engine as qwen_engine, make_voice
from app.voice import push_to_talk as ptt
from app.voice.mic_stream import MicStream, Interrupted
from app.voice.stt_whisper import (
    WhisperSTT,
    load_allowed_languages,
    CONFIG as STT_CONFIG,
)
from supertonic.config import AVAILABLE_LANGUAGES as TTS_LANGUAGES
from app.core.assistant_common import Cancelled, SpeechChunker, unload_ollama_model, ensure_models_installed
from app.core import voice_settings
from app.voice import wake_word_utils as ww
from app.core.assistant_engine import (
    get_all_configs,
    ask as ask_assistant,
    voice_config_for,
    reply_wav_for,
)

# ══════════════════════════════════════════════════════════════════════
# PLANTILLA DE PARÁMETROS — edita estos valores cuando quieras
# ══════════════════════════════════════════════════════════════════════
CONFIG = {
    # Umbral de similitud (0-1) para reconocer el nombre pese a errores de
    # transcripción de Whisper (p. ej. "harvis", "yarvis", "yervis", "vella",
    # "beya"...). Tolerante a propósito; las palabras comunes que por eso
    # se parecen demasiado a un nombre ("ella" ~ "bella" = 0.89) se bloquean
    # en la sección [excluir] de wake_words.txt en vez de subir el umbral.
    "wake_word_ratio": ww.DEFAULT_RATIO,

    # Segundos que se espera el comando después de decir solo el nombre
    # ("Jarvis" ... <pitido> ... "qué hora es").
    "followup_timeout": 6.0,

    # Segundos de silencio dentro de una conversación ya activa antes de
    # cerrarla y volver a exigir el nombre. Mientras la sesión está abierta
    # no hace falta repetir "Jarvis"/"Bella" en cada turno.
    "session_timeout": 5.0,

    # Tono del pitido de reconocimiento (frecuencia Hz, duración ms).
    "ack_beep": (880, 150),

    # Trocear la respuesta por oraciones y reproducirla en streaming (un
    # hilo sintetiza la oración siguiente mientras suena la actual) en vez
    # de sintetizar toda la respuesta de un jalón antes de reproducir nada.
    # Medido con Supertonic-3 (ver conversación): con una respuesta de 3
    # oraciones, el tiempo hasta el primer audio bajó de ~12s a ~5s, y el
    # RTF total mejoró de 0.90x a 0.76x (menos cómputo total, no solo
    # percepción) — probablemente porque el costo de atención del modelo
    # crece peor que lineal con la duración de la secuencia.
    # Si algo se siente peor (cortes raros entre oraciones, etc.), poner en
    # False vuelve al comportamiento anterior (una sola síntesis por
    # respuesta) sin tocar nada más.
    "tts_chunking": True,

    # Tamaño mínimo (caracteres) de cada trozo antes de cortar a la
    # siguiente oración; evita fragmentos sueltos muy cortos ("Sí." "Ok.")
    # que pagarían el costo fijo por llamada de síntesis sin ganar nada.
    # Con 15 casi cualquier oración normal ya se vuelve su propio trozo
    # (mayor beneficio de streaming); solo se fusiona con la siguiente si
    # de verdad es muy cortita.
    "tts_chunk_min_chars": 15,

    # Archivo donde el usuario puede limitar a qué idiomas se restringe el
    # pipeline (uno por línea, ver el archivo para más detalle). Si está
    # vacío o no tiene códigos válidos, se usan automáticamente TODOS los
    # idiomas que soportan a la vez Whisper (STT) y Supertonic-3 (TTS) — ver
    # `_resolve_allowed_languages()`.
    "languages_file": paths.LANGUAGES_TXT,

    # Archivo donde el usuario puede agregar a mano variantes/apodos que
    # también cuenten como el nombre de cada asistente (una sección por
    # asistente) y palabras que nunca deben activarlos por parecido
    # ([excluir]), ver el archivo. Se suma a la coincidencia difusa
    # automática que ya existe (wake_word_ratio) — ver `detect_wake_word()`.
    "wake_words_file": ww.WAKE_WORDS_PATH,
}
# ══════════════════════════════════════════════════════════════════════

# Un asistente por cada sección de assistants.yaml — no hay nada
# hardcodeado aquí, así que agregar/quitar un asistente es cuestión de
# editar ese archivo (ver assistant_engine.py). Todas las voces comparten
# un solo modelo Supertonic (ver supersonictts.shared_tts).
_ASSISTANT_CONFIGS = get_all_configs()
ASSISTANTS = {
    name: {
        "config": cfg,
        "voice": make_voice(voice_config_for(cfg)),  # Supertonic o voz clonada (Qwen3-TTS)
        "wav": reply_wav_for(name),
        "history": [],
        "label": cfg["label"],
        "ollama_model": cfg["base_model"],
        # Idiomas efectivos en los que responde (cfg["languages"] cruzado
        # con lo que soportan STT+TTS) — se fija en main(), ver
        # _resolve_allowed_languages().
        "languages": set(),
        # Idioma en que va la conversación con ESTE asistente: es la pista
        # para Whisper en su próximo turno (cada uno tiene la suya).
        "last_lang": None,
        # Cómo se lo llama: por su nombre y/o manteniendo apretada su tecla.
        "wake_word": cfg["wake_word"],
        "ptt_key": cfg["push_to_talk_key"],
    }
    for name, cfg in _ASSISTANT_CONFIGS.items()
}

# El micrófono queda abierto toda la sesión (ver mic_stream.py): así no se
# pierde lo que se dice entre una escucha y la siguiente.
MIC = MicStream(STT_CONFIG)

# Interrupción mientras el asistente habla (barge-in): kind "wake" = dijeron
# un nombre (name/text/lang = asistente, resto de la frase, idioma); kind
# "ptt" = apretaron la tecla de push to talk de `name`.
Interrupt = namedtuple("Interrupt", "kind name text lang")


def _ptt_pressed():
    """Nombre del asistente cuya tecla de push to talk está apretada ahora
    mismo, o None. Se le pasa a MIC.listen() como `interrupt`."""
    for name, assistant in ASSISTANTS.items():
        if assistant["ptt_key"] and ptt.is_pressed(assistant["ptt_key"]):
            return name
    return None


def _hint_for(name: str) -> str:
    """Idioma en que va la conversación con `name` (o su idioma por
    defecto): la pista de Whisper para lo que se le diga a él."""
    assistant = ASSISTANTS[name]
    return assistant["last_lang"] or assistant["config"]["language"]


def _transcribe_for(stt, audio, name: str):
    """Transcribe un turno dirigido a `name` (con su pista de idioma)."""
    text, lang = stt.transcribe(audio, hint=_hint_for(name), languages=ASSISTANTS[name]["languages"] or None)
    return text.strip(), lang


def _transcribe_addressed(stt, audio, ratio_threshold: float):
    """Transcribe una frase de la que todavía no se sabe a quién va
    dirigida. Devuelve (texto, idioma, asistente o None, resto).

    Sin pista de idioma: decide la detección de Whisper. Si la frase
    empieza con el nombre de un asistente y la detección fue dudosa, se
    transcribe otra vez con la pista y los idiomas de ESE asistente (antes
    se usaba la pista del último turno de cualquiera, y lo último hablado
    con BELLA en portugués sesgaba lo siguiente dicho a JARVIS)."""
    text, lang = stt.transcribe(audio)
    text = text.strip()
    name, remainder = detect_wake_word(text, ratio_threshold) if text else (None, None)
    if name and not stt.last_confident:
        langs = ASSISTANTS[name]["languages"]
        if lang != _hint_for(name) or (langs and lang not in langs):
            text2, lang2 = _transcribe_for(stt, audio, name)
            name2, remainder2 = detect_wake_word(text2, ratio_threshold)
            if name2 == name:
                text, lang, remainder = text2, lang2, remainder2
    return text, lang, name, remainder


def _ptt_turn(stt, name: str):
    """Graba mientras la tecla de `name` siga apretada y lo transcribe.
    Devuelve (texto, idioma); texto vacío si fue un toque sin habla."""
    key = ASSISTANTS[name]["ptt_key"]
    print(f"({ASSISTANTS[name]['label']}: push to talk [{key}], listening while held down…)")
    audio = ptt.record_while_pressed(key, MIC)
    ptt.wait_until_released(key)
    if audio is None:
        return "", None
    return _transcribe_for(stt, audio, name)

# Variantes/apodos de wake-word por asistente y palabras excluidas, cargadas
# de wake_words.txt al arrancar (ver main() y load_wake_word_aliases()).
# Vacíos hasta entonces: detect_wake_word() sigue funcionando igual (solo
# coincidencia difusa automática) si ese archivo no se cargó o no tiene nada.
WAKE_ALIASES = {name: set() for name in ASSISTANTS}
WAKE_EXCLUSIONS = set()


def load_wake_word_aliases(path: str):
    """Lee wake_words.txt (formato en wake_word_utils.py). Devuelve
    ({asistente: set(variantes)}, set(exclusiones)), todo normalizado
    (minúsculas, sin tildes); las secciones de asistentes que no existen en
    assistants.yaml se ignoran."""
    aliases, exclusions = ww.load_wake_words(path)
    return {name: aliases.get(name, set()) for name in ASSISTANTS}, exclusions


def detect_wake_word(text: str, ratio_threshold: float):
    """Busca el nombre de algún asistente al inicio de `text` (tolerando
    errores de transcripción y en cualquier alfabeto, ver
    wake_word_utils.find_wake_word). Devuelve (nombre, resto_del_texto) o
    (None, None). Cuentan el nombre real y las variantes de WAKE_ALIASES;
    las palabras de WAKE_EXCLUSIONS ("ella", "bello"...) nunca cuentan como
    parecido aproximado. Los asistentes con `wake_word: false` (solo push
    to talk) no se buscan."""
    names = {
        name: {ww.normalize(name)} | WAKE_ALIASES.get(name, set())
        for name, assistant in ASSISTANTS.items() if assistant["wake_word"]
    }
    return ww.find_wake_word(text, names, WAKE_EXCLUSIONS, ratio_threshold)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _split_into_speech_chunks(text: str, min_chars: int) -> list:
    """Divide `text` en trozos de una o más oraciones completas, de al
    menos `min_chars` caracteres cada uno (para no pagar el costo fijo por
    llamada de síntesis en frases sueltas muy cortas). Si el texto es una
    sola oración (el caso más común en estos asistentes), devuelve un único
    trozo con el texto completo."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    if len(sentences) <= 1:
        return [text.strip()] if text.strip() else []

    chunks = []
    buf = ""
    for sentence in sentences:
        buf = f"{buf} {sentence}".strip() if buf else sentence
        if len(buf) >= min_chars:
            chunks.append(buf)
            buf = ""
    if buf:
        if chunks:
            chunks[-1] = f"{chunks[-1]} {buf}".strip()
        else:
            chunks.append(buf)
    return chunks


def _safe_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


class _ChunkPlayer:
    """Reproduce una secuencia de trozos de audio de forma CONTINUA: un solo
    stream de sonido persistente para toda la respuesta, en vez de una
    llamada a winsound.PlaySound por trozo (que abre/cierra el dispositivo
    cada vez y puede cortar la cola del trozo anterior si el cálculo de
    duración no es exacto al milisegundo) — eso era lo que causaba el
    "se escucha mal por un segundo" entre trozo y trozo."""

    def __init__(self, samplerate: int):
        self._stream = sd.OutputStream(samplerate=samplerate, channels=1, dtype="float32")
        self._stream.start()
        self._lock = threading.Lock()
        self._closed = False
        self._aborted = False

    def write(self, data):
        """Envía estas muestras al stream (bloquea al ritmo real de
        reproducción, así se van pasando los trozos sin hueco). No hace
        nada si ya se abortó."""
        if self._aborted:
            return
        try:
            self._stream.write(data)
        except sd.PortAudioError:
            pass  # se abortó justo mientras se escribía este trozo

    def finish(self):
        """Ya no hay más trozos: espera a que termine de sonar lo que ya se
        envió (sin cortar nada) y cierra el stream."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if not self._aborted:
                try:
                    self._stream.stop()  # bloquea hasta que el buffer se vacía de verdad
                except sd.PortAudioError:
                    pass
            try:
                self._stream.close()
            except sd.PortAudioError:
                pass

    def abort(self):
        """Corta la reproducción YA (barge-in), aunque queden datos por
        sonar. Seguro de llamar aunque `finish()` ya se haya llamado (o se
        esté llamando) desde otro hilo — gana el primero que llegue."""
        with self._lock:
            self._aborted = True
            if self._closed:
                return
            self._closed = True
            try:
                self._stream.abort()  # corta de inmediato, descarta el buffer pendiente
            except sd.PortAudioError:
                pass
            try:
                self._stream.close()
            except sd.PortAudioError:
                pass


_WRITE_BLOCK_FRAMES = 4410  # ~100ms a 44100Hz


def _feed_player(chunk_queue, player: _ChunkPlayer, cancel_event, stats: dict, stats_lock, finished_event):
    """Hilo que va sacando trozos de la cola y alimentándolos al
    `_ChunkPlayer` en orden. Corre aparte del hilo que sintetiza (productor)
    y del que escucha el micrófono (principal).

    Escribe cada trozo en bloques chicos (~100ms) en vez de de un jalón, y
    es el ÚNICO hilo que llama a player.write()/abort()/finish(): PortAudio
    no soporta que un hilo llame a abort()/close() mientras OTRO hilo está
    bloqueado dentro de un write() en curso sobre el mismo stream —
    hacerlo así (como una primera versión de este código) provocaba un
    segfault del intérprete al interrumpir repetido. Escribiendo en bloques
    chicos, este mismo hilo nota cancel_event entre bloques (~100ms de
    reacción, imperceptible) y se aborta a sí mismo — nunca hay dos hilos
    tocando el stream a la vez."""
    try:
        while True:
            item = chunk_queue.get()
            if item is None:
                break
            chunk_path, synth_s = item
            try:
                data, sr = sf.read(chunk_path, dtype="float32")
            finally:
                _safe_remove(chunk_path)
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != _PLAYBACK_SAMPLERATE:
                # Las voces clonadas (Qwen3-TTS) salen a 24 kHz: sin esto
                # sonarían aceleradas en un stream de 44,1 kHz.
                n = int(round(len(data) * _PLAYBACK_SAMPLERATE / sr))
                data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype("float32")
                sr = _PLAYBACK_SAMPLERATE
            with stats_lock:
                stats["synth"] += synth_s
                stats["audio"] += len(data) / sr
            if cancel_event.is_set():
                break
            for start in range(0, len(data), _WRITE_BLOCK_FRAMES):
                if cancel_event.is_set():
                    break
                player.write(data[start:start + _WRITE_BLOCK_FRAMES])
            if cancel_event.is_set():
                break
    finally:
        if cancel_event.is_set():
            player.abort()
        else:
            player.finish()
        finished_event.set()


def _drain_chunk_queue(chunk_queue, wait_seconds: float = 0.5):
    """Tras cancelar, recoge (y borra del disco) los trozos que el
    productor ya hubiera puesto en la cola o esté a punto de poner, sin
    quedarse esperando más de `wait_seconds` en total."""
    deadline = time.monotonic() + wait_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            item = chunk_queue.get(timeout=remaining)
        except queue.Empty:
            return
        if item is None:
            return  # centinela: el productor ya terminó, no va a poner nada más
        chunk_path, _synth_s = item
        _safe_remove(chunk_path)


def _listen_while_playing(stt, ratio_threshold: float, finished_event, poll_timeout: float = 0.5):
    """Escucha el micrófono mientras `finished_event` no esté activo (la
    reproducción sigue sonando), descartando en silencio todo lo que no
    empiece por "jarvis"/"bella" (eco propio, ruido, otra conversación...).
    Devuelve un Interrupt si detecta un nombre o si apretaron una tecla de
    push to talk, o None si `finished_event` se activa (terminó de hablar)
    sin que lo interrumpieran."""
    while not finished_event.is_set():
        audio = MIC.listen(timeout=poll_timeout, interrupt=_ptt_pressed)
        if isinstance(audio, Interrupted):
            return Interrupt("ptt", audio.value, None, None)
        if audio is None:
            continue  # nada detectado en este tramo corto; se reevalúa finished_event

        _heard, heard_lang, name, remainder = _transcribe_addressed(stt, audio, ratio_threshold)
        if name is None:
            continue  # no era el nombre (eco propio / ruido / otra cosa): se ignora

        return Interrupt("wake", name, remainder, heard_lang)
    return None


def _log_rtf(synth_seconds: float, audio_seconds: float, note: str = ""):
    """Loguea el RTF (tiempo de síntesis / duración de audio) de la
    respuesta COMPLETA, sumando todos los trozos si se trocéo — no el RTF
    de cada trozo por separado (eso ya lo loguea supersonictts.py línea por
    línea)."""
    if audio_seconds <= 0:
        return
    rtf = synth_seconds / audio_seconds
    suffix = f" ({note})" if note else ""
    print(f"⏱ Total reply RTF: {synth_seconds:.2f}s compute / {audio_seconds:.2f}s audio = {rtf:.2f}x{suffix}")


_PLAYBACK_SAMPLERATE = 44100  # la de Supertonic (las voces clonadas, a 24 kHz, se remuestrean)


def _speak_chunks_with_barge_in(voice, chunks: list, wav_path: str, stt, ratio_threshold: float, lang: str):
    """Sintetiza `chunks` en un hilo aparte (uno detrás de otro, guardando
    cada uno en su propio archivo temporal) y los reproduce en un stream de
    audio CONTINUO (ver `_ChunkPlayer`) mientras el hilo principal escucha
    el micrófono — así el primer trozo empieza a sonar sin esperar a tener
    sintetizada toda la respuesta, y no hay huecos audibles entre trozos.
    Si se detecta el nombre mientras suena, se corta ahí mismo, se le avisa
    al hilo productor que pare y se descarta lo que faltaba (sin sintetizar
    ni reproducir de más). Funciona igual con 1 solo trozo (respuesta
    corta) que con varios.

    Devuelve un Interrupt si lo interrumpieron (nombre o push to talk), o
    None si terminó de hablar sin que lo interrumpieran.
    """
    base, ext = os.path.splitext(wav_path)
    # Lo que sonó mientras el modelo pensaba no se atiende (como siempre); y
    # mientras habla, su propia voz no cuenta como ruido ambiente (si no, el
    # umbral subiría y costaría más interrumpirlo).
    MIC.flush()
    MIC.freeze_noise(True)

    chunk_queue = queue.Queue()
    cancel_event = threading.Event()
    finished_event = threading.Event()
    stats = {"synth": 0.0, "audio": 0.0}
    stats_lock = threading.Lock()

    def producer():
        for i, chunk_text in enumerate(chunks):
            if cancel_event.is_set():
                break
            chunk_path = f"{base}.chunk{i}{ext}"
            t0 = time.time()
            try:
                voice.speak(chunk_text, chunk_path, lang=lang)
            except Exception as e:
                print(f"(error synthesizing chunk {i}: {e})")
                break
            synth_s = time.time() - t0
            if cancel_event.is_set():
                _safe_remove(chunk_path)
                break
            chunk_queue.put((chunk_path, synth_s))
        chunk_queue.put(None)  # centinela: no hay más trozos

    producer_thread = threading.Thread(target=producer, daemon=True)
    producer_thread.start()

    player = _ChunkPlayer(_PLAYBACK_SAMPLERATE)
    player_thread = threading.Thread(
        target=_feed_player,
        args=(chunk_queue, player, cancel_event, stats, stats_lock, finished_event),
        daemon=True,
    )
    player_thread.start()

    try:
        result = _listen_while_playing(stt, ratio_threshold, finished_event)
    finally:
        MIC.freeze_noise(False)

    if result is not None:
        # OJO: nunca llamar aquí a player.abort() directamente — el hilo
        # reproductor (_feed_player) es el ÚNICO que debe tocar el stream
        # (ver por qué en su docstring). Solo se avisa con cancel_event y
        # se espera a que ese hilo lo note y cierre el stream él mismo.
        cancel_event.set()
        finished_event.wait(timeout=1.0)
        _drain_chunk_queue(chunk_queue)
        with stats_lock:
            _log_rtf(stats["synth"], stats["audio"], note="cut short by interruption")
        return result

    with stats_lock:
        _log_rtf(stats["synth"], stats["audio"])
    return None


def speak_with_barge_in(voice, text: str, wav_path: str, stt, ratio_threshold: float, lang: str = None):
    """Sintetiza `text` (en `lang`, ver `JarvisVoice.speak`) y lo reproduce
    SIN bloquear, escuchando el micrófono en paralelo mientras suena.
    Cualquier frase captada que no empiece por "jarvis"/"bella" se descarta
    en silencio (evita que el propio eco del asistente por el micrófono se
    interprete como un comando); si sí coincide con un nombre, corta el
    audio al instante.

    Si CONFIG["tts_chunking"] está activo y la respuesta tiene más de una
    oración, se sintetiza y reproduce por trozos en streaming (ver
    `_speak_chunks_with_barge_in`) en vez de esperar a tener toda la
    respuesta lista. El barge-in funciona igual; el chequeo de interrupción
    simplemente corre a través de los cortes entre trozos. Apretar la tecla
    de push to talk de cualquier asistente también lo corta.

    Devuelve un Interrupt si lo interrumpieron, o None si terminó de hablar
    sin que lo interrumpieran.
    """
    if CONFIG["tts_chunking"]:
        chunks = _split_into_speech_chunks(text, CONFIG["tts_chunk_min_chars"]) or [text]
    else:
        chunks = [text]
    return _speak_chunks_with_barge_in(voice, chunks, wav_path, stt, ratio_threshold, lang)


def handle_command(stt, name: str, command: str, lang: str = None):
    assistant = ASSISTANTS[name]
    print(f"You ({assistant['label']})> {command}")

    history = assistant["history"]
    cfg = assistant["config"]
    # Le hablaron en un idioma que otro asistente sí tiene habilitado (por
    # eso Whisper lo detectó) pero este no: responde en su idioma por
    # defecto.
    if lang not in assistant["languages"]:
        lang = cfg["language"]
    history.append({"role": "user", "content": command})

    def _announce_search(tool_name):
        if tool_name == "web_search":
            wav_path = assistant["voice"].speak(cfg["search_announcement"], assistant["wav"])
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)

    if CONFIG["tts_chunking"]:
        return _handle_streaming(stt, name, history, cfg, lang, _announce_search)

    try:
        reply = ask_assistant(name, history, on_tool_call=_announce_search, reply_lang=lang, cfg=cfg)
    except requests.exceptions.ConnectionError:
        print("Cannot connect to Ollama. Is the service running ('ollama serve')?")
        history.pop()
        return None
    except requests.exceptions.RequestException as e:
        # Timeout, error HTTP (4xx/5xx), respuesta corrupta, etc. — no solo
        # ConnectionError. Se avisa y se sigue en vez de dejar que la
        # excepción suba sin control hasta main() (que igual limpiaría bien
        # al salir, pero así el asistente sigue disponible para el próximo
        # turno en vez de cortar toda la sesión).
        print(f"(Ollama request failed: {e}. Please try again.)")
        history.pop()
        return None

    history.append({"role": "assistant", "content": reply})
    history[:] = history[-cfg["max_history"]:]
    assistant["last_lang"] = lang

    print(f"{assistant['label']}> {reply}")
    return speak_with_barge_in(
        assistant["voice"], reply, assistant["wav"], stt, CONFIG["wake_word_ratio"], lang=lang
    )


def _handle_streaming(stt, name, history, cfg, lang, on_tool_call):
    """Como handle_command, pero la respuesta llega en streaming
    (ask_with_tools con on_text) y cada frase se sintetiza y suena apenas
    está completa, en cola, sin esperar el texto entero. Si lo interrumpen
    (nombre o push to talk) se corta también la generación (Cancelled).
    Lo que el motor descarta ("reset") ya no se puede desdecir aquí: se
    sigue con lo nuevo."""
    assistant = ASSISTANTS[name]
    sentences = queue.Queue()
    chunker = SpeechChunker(min_chars=CONFIG["tts_chunk_min_chars"])
    cancel = threading.Event()
    result = {}

    def on_text(kind, text):
        if cancel.is_set():
            raise Cancelled()
        if kind == "reset":
            chunker.reset()
            return
        for sentence in chunker.feed(text):
            sentences.put(sentence)

    def worker():
        try:
            result["reply"] = ask_assistant(name, history, on_tool_call=on_tool_call, reply_lang=lang,
                                            cfg=cfg, on_text=on_text)
            for sentence in chunker.flush():
                sentences.put(sentence)
        except Cancelled:
            pass
        except Exception as e:  # noqa: BLE001 — se informa abajo, en el hilo principal
            result["error"] = e
        finally:
            sentences.put(None)

    def stream():
        while True:
            sentence = sentences.get()
            if sentence is None:
                return
            yield sentence

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    intr = _speak_chunks_with_barge_in(assistant["voice"], stream(), assistant["wav"], stt, CONFIG["wake_word_ratio"], lang)
    if intr is not None:
        cancel.set()
    thread.join(timeout=5)
    error = result.get("error")
    if isinstance(error, requests.exceptions.ConnectionError):
        print("Cannot connect to Ollama. Is the service running ('ollama serve')?")
    elif isinstance(error, requests.exceptions.RequestException):
        print(f"(Ollama request failed: {error}. Please try again.)")
    elif error is not None:
        print(f"(error generating reply: {error})")
    reply = result.get("reply")
    if reply is None:
        if intr is None:
            history.pop()
        return intr
    history.append({"role": "assistant", "content": reply})
    history[:] = history[-cfg["max_history"]:]
    assistant["last_lang"] = lang
    print(f"{assistant['label']}> {reply}")
    return intr


def run_session(stt, name: str, command: str, lang: str = None):
    """Mantiene una conversación continua con `name`: tras el nombre inicial,
    cada turno siguiente NO necesita repetirlo mientras se hable dentro de
    `session_timeout` segundos. Se cierra sola (y hay que volver a llamar al
    asistente por su nombre) en cuanto pasa ese tiempo en silencio.

    `lang` es el idioma (código ISO 639-1) detectado en `command`; se
    reevalúa en cada turno con lo que Whisper detecte en esa frase, para que
    la respuesta (texto y voz) siga el idioma que se use en cada momento.

    Si a mitad de la respuesta lo interrumpen diciendo un nombre o apretando
    una tecla de push to talk (barge-in, ver `speak_with_barge_in`), esa
    interrupción se atiende como si fuera el siguiente turno, en vez de
    esperar a que termine de hablar.

    Un asistente solo de push to talk (`wake_word: false`) no deja la sesión
    abierta: cada turno es apretando su tecla otra vez."""
    while command:
        intr = handle_command(stt, name, command, lang)

        if intr is None and not ASSISTANTS[name]["wake_word"]:
            return  # solo push to talk: sin micrófono abierto después de responder

        if intr is None:
            audio = MIC.listen(timeout=CONFIG["session_timeout"], interrupt=_ptt_pressed)
            if isinstance(audio, Interrupted):
                intr = Interrupt("ptt", audio.value, None, None)

        if intr is not None:
            if intr.name != name:
                print(f"(switching conversation to {ASSISTANTS[intr.name]['label']})")
            name = intr.name
            if intr.kind == "ptt":
                text, lang = _ptt_turn(stt, name)
                if not text:
                    return
            else:
                text, lang = intr.text, intr.lang
        else:
            if audio is None:
                print(f"({ASSISTANTS[name]['label']}: session closed due to silence, call by name again)")
                return

            text, lang = _transcribe_for(stt, audio, name)
            if not text:
                return

            # Si dentro de la sesión se nombra al OTRO asistente, se cambia
            # de conversación en caliente en vez de ignorarlo.
            other_name, remainder = detect_wake_word(text, CONFIG["wake_word_ratio"])
            if other_name and other_name != name:
                print(f"(switching conversation to {ASSISTANTS[other_name]['label']})")
                name = other_name
                text = remainder

        if not text:
            winsound.Beep(*CONFIG["ack_beep"])
            MIC.flush()  # que el propio pitido no cuente como el comando
            audio = MIC.listen(timeout=CONFIG["followup_timeout"])
            if audio is None:
                return
            text, lang = _transcribe_for(stt, audio, name)
            if not text:
                return

        command = text


def _resolve_allowed_languages(stt) -> set:
    """Calcula a qué idiomas se restringe el reconocimiento/síntesis:
    interseca lo que Whisper puede reconocer con lo que Supertonic-3 puede
    hablar (así nunca se "detecta" un idioma que la voz no puede
    pronunciar), y si `CONFIG["languages_file"]` tiene códigos propios, los
    usa en vez de esa lista completa — descartando (con aviso) cualquiera
    que ninguno de los dos modelos soporte en realidad.

    Además fija ASSISTANTS[x]["languages"] con los idiomas de cada asistente
    (`languages` en assistants.yaml, vacío = todos) y devuelve la UNIÓN de
    todos: Whisper tiene que poder detectar cualquier idioma que hable
    alguno de los asistentes, porque el idioma se detecta antes de saber a
    quién se le está hablando."""
    default_set = set(TTS_LANGUAGES) - {"na"}
    default_set &= set(stt.supported_languages())

    base = default_set
    user_set = load_allowed_languages(CONFIG["languages_file"])
    if user_set:
        invalid = user_set - default_set
        if invalid:
            print(
                f"(warning: languages.txt contains languages unsupported by STT+TTS, ignoring: {', '.join(sorted(invalid))})"
            )
        base = (user_set & default_set) or default_set

    union = set()
    for name, assistant in ASSISTANTS.items():
        own = set(assistant["config"]["languages"])
        invalid = own - base
        if invalid:
            print(f"(warning: {name} has unavailable languages configured, ignoring: {', '.join(sorted(invalid))})")
        assistant["languages"] = (own & base) or base
        union |= assistant["languages"]
    return union or base


def cleanup(stt):
    """Limpieza completa al salir: cierra el micrófono, libera los modelos
    cargados en este proceso (Whisper y Supertonic) y le pide a Ollama que
    descargue los modelos de los asistentes de inmediato. Sin esto último,
    Ollama corre como servicio aparte y mantiene el modelo en RAM/VRAM
    (keep_alive) aunque este script ya haya terminado."""
    print("\nUnloading models from memory...")

    MIC.close()
    stt._model = None
    for assistant in ASSISTANTS.values():
        assistant["voice"].release()
    release_shared_tts()
    qwen_engine().release()
    for model in sorted({a["ollama_model"] for a in ASSISTANTS.values()}):
        unload_ollama_model(model)

    gc.collect()
    print("Models unloaded.")


def main():
    global WAKE_ALIASES, WAKE_EXCLUSIONS

    ensure_models_installed(_ASSISTANT_CONFIGS)

    # El Whisper elegido en Ajustes compartidos (ligero o pesado).
    stt = WhisperSTT({**STT_CONFIG, "model_size": voice_settings.stt_model()})
    stt._load()  # carga el modelo al arrancar, no en la primera frase
    for assistant in ASSISTANTS.values():
        assistant["voice"]._load()  # ídem para la voz (un solo modelo para todas)
    # Voces clonadas: Qwen3-TTS se prepara en segundo plano (puede tardar
    # minutos); mientras, esos asistentes hablan con su voz de respaldo.
    if any(voice_settings.is_custom(a["config"]["voice"]) for a in ASSISTANTS.values()):
        qwen_engine().warm_up_async()

    stt.allowed_languages = _resolve_allowed_languages(stt)
    print(f"Active languages: {', '.join(sorted(stt.allowed_languages))}")
    for assistant in ASSISTANTS.values():
        if assistant["languages"] != stt.allowed_languages:
            print(f"  {assistant['label']}: {', '.join(sorted(assistant['languages']))}")

    WAKE_ALIASES, WAKE_EXCLUSIONS = load_wake_word_aliases(CONFIG["wake_words_file"])
    for name, aliases in WAKE_ALIASES.items():
        if aliases:
            print(f"Loaded wake-word aliases for \"{name}\": {', '.join(sorted(aliases))}")
    if WAKE_EXCLUSIONS:
        print(f"Words excluded from fuzzy wake matching: {', '.join(sorted(WAKE_EXCLUSIONS))}")
    print()

    freq, dur = CONFIG["ack_beep"]

    ways = [f"say '{name.capitalize()}'" for name, a in ASSISTANTS.items() if a["wake_word"]]
    ways += [f"hold {a['ptt_key']} ({a['label']})" for a in ASSISTANTS.values() if a["ptt_key"]]
    MIC.open()
    print(f"\nReady. To talk to an assistant: {', '.join(ways)} (Ctrl+C to quit).\n")
    try:
        while True:
            try:
                audio = MIC.listen(interrupt=_ptt_pressed)
                if isinstance(audio, Interrupted):
                    command, lang = _ptt_turn(stt, audio.value)
                    if command:
                        run_session(stt, audio.value, command, lang)
                    continue
                if audio is None:
                    continue  # ruido/click puntual descartado por duración mínima
                text, lang, name, remainder = _transcribe_addressed(stt, audio, CONFIG["wake_word_ratio"])
                if not text:
                    continue
                if name is None:
                    print(f"(ignored: {text})")
                    continue

                command = remainder
                if not command:
                    winsound.Beep(freq, dur)
                    MIC.flush()  # que el propio pitido no cuente como el comando
                    audio = MIC.listen(timeout=CONFIG["followup_timeout"])
                    if audio is None:
                        print(f"({ASSISTANTS[name]['label']}: no command heard)")
                        continue
                    command, lang = _transcribe_for(stt, audio, name)
                    if not command:
                        continue

                run_session(stt, name, command, lang)

            except KeyboardInterrupt:
                break
    except KeyboardInterrupt:
        pass  # por si el Ctrl+C llega fuera del try interno (p. ej. durante la captura de audio)
    finally:
        cleanup(stt)

    print("Goodbye.")


if __name__ == "__main__":
    main()
