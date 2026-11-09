"""
STT (voz -> texto) para los asistentes JARVIS y BELLA.
Usa faster-whisper (motor CTranslate2) para transcribir. La captura del
micrófono (stream continuo + VAD por energía) está en mic_stream.py; aquí
están sus parámetros (CONFIG) junto con los de Whisper.

Uso:
    from app.voice.mic_stream import MicStream
    from app.voice.stt_whisper import WhisperSTT, CONFIG

    stt = WhisperSTT()
    with MicStream(CONFIG) as mic:
        audio = mic.listen()                  # bloquea hasta capturar una frase
        if audio is not None:
            texto, idioma = stt.transcribe(audio)  # idioma: código ISO 639-1 detectado

Ejecutado directamente (`python stt_whisper.py`) hace una prueba: escucha una
frase por el micrófono y muestra la transcripción.
"""
import math
import os
import re
import sys
import time

import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ctranslate2 (motor de faster-whisper) necesita cuBLAS/cuDNN de CUDA 12, que
# no vienen con el resto del entorno (torch trae su propio CUDA 13). Se
# instalan como paquetes pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) en vez de
# requerir el CUDA Toolkit del sistema, así que hay que añadir sus carpetas
# "bin" al buscador de DLLs de Windows antes de cargar el modelo en GPU.
# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.voice import cuda_setup  # noqa: E402
from app.core.text_language import detect as _text_language  # noqa: E402

cuda_setup.add_nvidia_dll_dirs()

from faster_whisper import WhisperModel

# ══════════════════════════════════════════════════════════════════════
# PLANTILLA DE PARÁMETROS — edita estos valores cuando quieras
# ══════════════════════════════════════════════════════════════════════
CONFIG = {
    # Tamaño del modelo Whisper: "tiny", "base", "small", "medium", "large-v3"
    # (a más grande, más precisión y más lento). "small" es un buen punto
    # intermedio para español en GPU.
    "model_size": "small",

    # Hardware. Si CUDA falla al cargar, se cae automáticamente a CPU.
    "device": "cuda",
    "compute_type": "float16",   # usado si device == "cuda"
    "cpu_compute_type": "int8",  # usado en el fallback a CPU

    # Idioma de transcripción. None = autodetectar en cada frase (medido:
    # el costo extra frente a fijarlo es despreciable con el modelo "small").
    # Autodetectar permite que voice_loop.py responda en el idioma que
    # hable el usuario en cada turno (ver transcribe(), que devuelve
    # (texto, idioma_detectado)). Poner un código ISO 639-1 aquí (p. ej.
    # "es") en vez de None fuerza siempre ese idioma.
    "language": None,

    # Si la confianza de la detección de idioma es menor a esto (frases muy
    # cortas tipo "sí"/"gracias" dan poca señal), se usa "fallback_language"
    # en vez del detectado, para no cambiarle el idioma a las respuestas por
    # una detección poco fiable.
    "min_language_confidence": 0.5,
    "fallback_language": "es",

    # Elección del idioma con idiomas permitidos (allowed_languages). Ojo:
    # forzarle a Whisper un idioma que no es el que se habló hace que
    # TRADUZCA lo dicho a ese idioma, así que ante la duda (acento, frase
    # corta) no se fuerza uno por defecto: se transcribe en los candidatos
    # (el más probable, el 2º si la detección no es clara y el idioma de la
    # conversación, `hint`) y gana el de mejor puntaje (ver transcribe()).
    # Valores elegidos midiendo 88 frases en inglés/portugués/español con
    # acento y ruido: con el idioma de la conversación igual al hablado,
    # acierta 86/88 (forzando "es" ante la duda, como antes: 61/88).
    "confident_language": 0.8,      # desde aquí la detección se da por clara
    "candidate_min_prob": 0.05,     # un 2º candidato por debajo de esto ni se prueba
    "hint_bonus": 0.15,             # ventaja del idioma de la conversación
    "detection_weight": 0.05,       # peso de la probabilidad de detección en el puntaje
    "leak_penalty": 0.4,            # forzado a X pero el texto salió en otro idioma
    "noise_logprob": -1.0,          # por debajo (y con detección < 0.25): ruido, no habla

    # ── Captura de audio (micrófono) ──
    "samplerate": 16000,
    "device_index": None,     # None = micrófono por defecto del sistema;
                               # usa el índice de `sd.query_devices()` para elegir otro
    "block_ms": 30,            # tamaño de cada bloque de audio analizado (ms)
    "calibration_seconds": 0.5,     # al abrir el micrófono, tiempo para medir el ruido ambiente
                                    # (después se sigue midiendo solo, ver mic_stream.py)
    "threshold_multiplier": 3.0,    # umbral de voz = ruido ambiente * este factor
    "min_threshold": 0.008,         # umbral mínimo, por si el ambiente es muy silencioso
    "silence_timeout": 1.6,         # segundos de silencio para dar la frase por terminada
                                    # (con 0.8 una pausa para pensar cortaba la pregunta)
    "max_utterance_seconds": 25.0,  # duración máxima de una sola frase capturada
    "min_speech_seconds": 0.35,     # push to talk: un toque más corto que esto no es habla
    "min_voiced_seconds": 0.12,     # VAD: con menos voz que esto (por encima del umbral) es un
                                    # golpe/click suelto, no habla ("sí" ya pasa de sobra)

    # ── Filtros anti-alucinación de Whisper ──
    # Whisper "inventa" texto (típicamente frases genéricas de vídeos de
    # YouTube, como "nos vemos en el próximo vídeo") cuando el audio es
    # silencio o ruido de fondo sin habla real. Estos parámetros se pasan
    # directo a model.transcribe() para reducirlo.
    "no_speech_threshold": 0.6,
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "condition_on_previous_text": False,  # evita que un error se autorrefuerce y se repita
}
# ══════════════════════════════════════════════════════════════════════


def _is_repetition_hallucination(text: str) -> bool:
    """Detecta el patrón típico de alucinación de Whisper: la misma frase de
    2+ palabras repetida 3+ veces seguidas (p. ej. "nos vemos en el próximo
    vídeo" x3). Nadie habla así de forma natural al dar un comando."""
    words = re.findall(r"\w+", text.lower())
    n = len(words)
    if n < 6:
        return False
    for phrase_len in range(2, 8):
        span = phrase_len * 3
        if n < span:
            break
        for start in range(0, n - span + 1):
            chunk = words[start:start + phrase_len]
            if (
                words[start + phrase_len:start + 2 * phrase_len] == chunk
                and words[start + 2 * phrase_len:start + span] == chunk
            ):
                return True
    return False


# Frases "de cierre de video de YouTube" que Whisper inventa de memoria
# (entrenado con subtítulos de YouTube) cuando el segmento es silencio o
# ruido de fondo sin habla real — vistas en la práctica incluso con
# vad_filter/no_speech_threshold/compression_ratio_threshold activados,
# que reducen pero no eliminan el problema del todo. Rasgo distintivo: son
# casi siempre en INGLÉS aunque el resto de la sesión sea en español (el
# corpus de entrenamiento de estas alucinaciones es mayormente en inglés),
# y suelen aparecer solas, como toda la transcripción, no mezcladas con
# habla real. Coincidencia parcial (in operator) porque a veces vienen
# concatenadas o con variaciones menores ("Thanks for watching. Have a
# nice day. Peace." combina tres de estos fragmentos en una).
_HALLUCINATION_PHRASES = [
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "like and subscribe",
    "don't forget to subscribe",
    "see you in the next video",
    "see you next time",
    "subtitles by",
    "transcribed by",
    "amara.org",
    "www.youtube.com",
    "gracias por ver el video",
    "gracias por ver este video",
    "no olvides suscribirte",
    "suscríbete al canal",
    "subtítulos por la comunidad",
    "subtítulos realizados por la comunidad",
    "subtitulado por la comunidad",
    "legendas pela comunidade",
    "obrigado por assistir",
]


def _is_known_hallucination_phrase(text: str) -> bool:
    """Descarta la transcripción si consiste (total o casi totalmente) en
    una de las frases de _HALLUCINATION_PHRASES. Nadie le da un comando así
    a un asistente de voz, así que un match es señal fuerte de que el
    "habla" detectada por el VAD de energía era en realidad silencio/ruido
    que Whisper alucinó en texto."""
    norm = _norm_phrase(text)
    if not norm:
        return False
    # Las frases se normalizan igual que el texto: antes "amara.org" nunca
    # coincidía porque al texto se le quitaba el punto ("amara org") y pasaba
    # "Subtítulos por la comunidad de Amara.org" como si lo hubiera dicho.
    return any(_norm_phrase(phrase) in norm for phrase in _HALLUCINATION_PHRASES)


def _norm_phrase(text: str) -> str:
    norm = re.sub(r"[^a-záéíóúñãõç\s]", " ", text.lower())
    return re.sub(r"\s+", " ", norm).strip()


_FILLER_RE = re.compile(
    r"^(m+|h?m+|e+h*|a+h*|u+h*|u+m+|o+h*|ah[aá]|aj[aá]|eh+m+|hmm+|mhm+|huh)$", re.I
)


def _is_filler(text: str) -> bool:
    """Solo muletillas o sonidos ("mmm", "eh", "ajá", "hmm"): no es un
    pedido. Antes "mmm" se mandaba al modelo como mensaje y respondía."""
    words = re.findall(r"[^\W\d_]+", text)
    return bool(words) and all(_FILLER_RE.match(w) for w in words)


def load_allowed_languages(path: str) -> set:
    """Lee un archivo de idiomas permitidos: un código ISO 639-1 por línea,
    '#' para comentarios/líneas vacías ignoradas. Devuelve un set con los
    códigos activos (en minúscula), o un set vacío si el archivo no existe
    o no tiene ningún código activo."""
    codes = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip().lower()
                if line:
                    codes.add(line)
    except FileNotFoundError:
        pass
    return codes


class WhisperSTT:
    """Carga el modelo Whisper una sola vez y transcribe audio bajo demanda."""

    def __init__(self, config: dict = None):
        self.config = config or CONFIG
        self._model = None
        # Si se fija (ver load_allowed_languages), transcribe() solo elige
        # entre estos idiomas al autodetectar en vez de entre los ~100 que
        # conoce Whisper — así nunca "detecta" un idioma que Supertonic (TTS)
        # no pueda hablar. Vacío/None = sin restricción (comportamiento
        # original: cualquier idioma que Whisper reconozca). transcribe()
        # acepta otra lista por llamada (los idiomas de UN asistente).
        self.allowed_languages = None
        # La pista de idioma (`hint`) ya no se recuerda aquí entre turnos:
        # con un solo valor para todos, lo último hablado con BELLA en
        # portugués sesgaba la frase siguiente dicha a JARVIS en español.
        # Cada quien que llama pasa la del asistente con quien se habla.
        #
        # Si la última detección de idioma fue clara (para decidir si vale
        # la pena repetir la transcripción con la pista de un asistente).
        self.last_confident = False
        # Cómo se decidió el idioma la última vez (para el log).
        self.last_detail = ""
        self.quality = {}  # idioma → qué tan seguro está Whisper de que oyó habla (ver _run)

    def _load(self):
        if self._model is not None:
            return self._model

        cfg = self.config
        print(f"Loading Whisper model ({cfg['model_size']}) ...")
        t0 = time.time()
        try:
            model = WhisperModel(
                cfg["model_size"],
                device=cfg["device"],
                compute_type=cfg["compute_type"],
            )
            # WhisperModel() no valida la GPU al construirse: si faltan
            # cuBLAS/cuDNN, el error solo aparece en la primera inferencia
            # real. Se fuerza aquí, con un audio de prueba, para poder caer a
            # CPU de forma segura en vez de fallar en la primera frase.
            list(model.transcribe(np.zeros(16000, dtype=np.float32), language=cfg["language"])[0])
            self._model = model
        except Exception as e:
            print(f"Could not use {cfg['device']} ({e}), falling back to CPU.")
            self._model = WhisperModel(
                cfg["model_size"],
                device="cpu",
                compute_type=cfg["cpu_compute_type"],
            )
        print(f"Model loaded in {time.time() - t0:.1f}s\n")
        return self._model

    def supported_languages(self) -> list:
        """Todos los idiomas que este modelo de Whisper puede reconocer (sin
        restringir por `allowed_languages`) — códigos ISO 639-1."""
        return self._load().supported_languages

    def _ranked_allowed(self, audio: np.ndarray, allowed: set) -> list:
        """[(idioma, probabilidad)] de los idiomas `allowed`, del más al
        menos probable, según `detect_language()` (más barato que una
        transcripción completa)."""
        try:
            _, _, all_probs = self._model.detect_language(audio, vad_filter=True)
        except Exception:
            all_probs = []
        return [(lang, prob) for lang, prob in all_probs if lang in allowed]

    def _run(self, audio: np.ndarray, language):
        """Transcribe en `language` (None = lo elige Whisper). Devuelve
        (texto, puntaje, info); el puntaje es la log-probabilidad media de
        los segmentos, ponderada por duración: qué tan natural le resulta a
        Whisper ese texto en ese idioma. Una "traducción" forzada puntúa
        claramente peor que la transcripción en el idioma real."""
        cfg = self.config
        segments, info = self._model.transcribe(
            audio,
            language=language,
            # VAD propio (energía) ya decide CUÁNDO grabar; este vad_filter
            # de Whisper (Silero) es una segunda pasada que recorta silencio/
            # ruido DENTRO del propio segmento, para no alucinar sobre él.
            vad_filter=True,
            no_speech_threshold=cfg["no_speech_threshold"],
            compression_ratio_threshold=cfg["compression_ratio_threshold"],
            log_prob_threshold=cfg["log_prob_threshold"],
            condition_on_previous_text=cfg["condition_on_previous_text"],
        )
        segments = list(segments)
        text = "".join(seg.text for seg in segments).strip()
        if not text:
            return "", float("-inf"), info
        weights = [max(seg.end - seg.start, 0.01) for seg in segments]
        score = sum(seg.avg_logprob * w for seg, w in zip(segments, weights)) / sum(weights)
        self.quality[language or info.language] = {
            "no_speech": min(seg.no_speech_prob for seg in segments), "logprob": score,
            "vad_seconds": getattr(info, "duration_after_vad", None) or 0.0,
        }
        return text, score, info

    def _candidates(self, audio: np.ndarray, hint, allowed: set) -> tuple:
        """(idiomas en los que vale la pena transcribir, detección). Solo el
        detectado si la detección es clara y coincide con la pista; si no,
        también el 2º más probable (si la detección duda) y la pista (el
        idioma de la conversación, que se prueba siempre que difiera: es lo
        que eligió el usuario o en lo que viene hablando)."""
        cfg = self.config
        ranked = self._ranked_allowed(audio, allowed)
        if not ranked:
            for lang in (hint, cfg["fallback_language"]):
                if lang in allowed:
                    return [lang], ranked
            return [sorted(allowed)[0]], ranked
        top, top_prob = ranked[0]
        candidates = [top]
        if top_prob < cfg["confident_language"] and len(ranked) > 1 and ranked[1][1] >= cfg["candidate_min_prob"]:
            candidates.append(ranked[1][0])
        if hint in allowed and hint not in candidates:
            candidates.append(hint)
        return candidates, ranked

    def transcribe(self, audio: np.ndarray, hint: str = None, languages=None):
        """audio: numpy float32 mono a la frecuencia configurada (samplerate).

        Devuelve (texto, idioma) — idioma como código ISO 639-1 (p. ej.
        "es", "en"). Si `CONFIG["language"]` está fijo, `idioma` es ese
        mismo valor. Si es None (autodetectar): con `self.allowed_languages`
        vacío, es el detectado libremente por Whisper (o `fallback_language`
        si la confianza es baja, ver `min_language_confidence`); con
        `allowed_languages` fijado, se restringe a esos idiomas (ver
        `_candidates`).

        `hint`: el idioma en que va la conversación con ESE asistente (o el
        elegido por el usuario); solo desempata cuando la detección es
        dudosa. Sin pista (todavía no se sabe a quién le hablan) decide la
        detección. `languages`: entre qué idiomas elegir en esta llamada (en
        vez de `allowed_languages`).

        Deja en `last_confident` si la detección de idioma fue clara."""
        self._load()
        cfg = self.config
        allowed = set(languages) if languages else self.allowed_languages

        if cfg["language"] is not None:
            lang = cfg["language"]
            text, _score, _info = self._run(audio, lang)
            self.last_detail = f"{lang} (fixed)"
            self.last_confident = True
        elif not allowed:
            text, _score, info = self._run(audio, None)
            prob = info.language_probability or 0.0
            lang = info.language or cfg["fallback_language"]
            if prob < cfg["min_language_confidence"]:
                lang = hint or cfg["fallback_language"]
            self.last_detail = f"{info.language} {prob:.2f}"
            self.last_confident = prob >= cfg["confident_language"]
        else:
            text, lang = self._transcribe_allowed(audio, hint, allowed)

        if _is_repetition_hallucination(text) or _is_known_hallucination_phrase(text) or _is_filler(text):
            return "", lang
        return text, lang

    def _transcribe_allowed(self, audio: np.ndarray, hint, allowed: set):
        """Transcribe en cada candidato y se queda con el de mejor puntaje:
        log-probabilidad media de Whisper (una traducción forzada puntúa
        peor que la transcripción en el idioma real), un poco de la
        probabilidad de detección, ventaja para la pista y castigo si el
        texto salió en otro idioma que el forzado. Con una sola palabra
        ("sí", "sim", "yes") el audio casi no dice nada del idioma: decide la
        pista salvo que la detección sea abrumadora."""
        cfg = self.config
        candidates, ranked = self._candidates(audio, hint, allowed)
        probs = dict(ranked)
        detected = ", ".join(f"{c} {p:.2f}" for c, p in ranked[:3]) or "no detection"
        self.last_confident = bool(ranked) and ranked[0][1] >= cfg["confident_language"]
        if len(candidates) == 1:
            lang = candidates[0]
            text, _score, _info = self._run(audio, lang)
            self.last_detail = f"{detected} → {lang}"
            return text, lang

        results = {}
        for cand in candidates:
            cand_text, score, _info = self._run(audio, cand)
            total = score + cfg["detection_weight"] * math.log(max(probs.get(cand, 0.0), 0.01))
            if cand == hint:
                total += cfg["hint_bonus"]
            leaked = _text_language(cand_text) if cand_text else None
            if leaked and leaked != cand:
                total -= cfg["leak_penalty"]
            results[cand] = (total, cand_text, score)

        top = ranked[0][0] if ranked else None
        # Ruido o voces de fondo: ningún idioma convence a la detección y
        # ninguna transcripción le resulta natural a Whisper. Visto: un audio
        # con detección "en 0.11" salió como "So, let's take a look at the
        # quality of the work." y el asistente respondió a eso.
        if (probs.get(top, 0.0) < 0.25
                and max(r[2] for r in results.values()) < cfg["noise_logprob"]):
            self.last_detail = f"detected {detected}; looks like noise, discarded"
            return "", hint or top
        one_word = max(len(re.findall(r"\w+", r[1])) for r in results.values()) <= 1
        if (one_word and hint in results and results[hint][1]
                and (top == hint or probs.get(top, 0.0) < 0.9)):
            lang, why = hint, "single-word phrase"
        else:
            lang, why = max(results, key=lambda c: results[c][0]), "best score"
        tried = ", ".join(f"{c} {r[0]:.2f}" for c, r in results.items())
        self.last_detail = f"detected {detected}; tried {tried} → {lang} ({why})"
        return results[lang][1], lang


if __name__ == "__main__":
    from app.voice.mic_stream import MicStream

    stt = WhisperSTT()
    stt._load()
    print("Speak near the microphone (or Ctrl+C to quit)...\n")
    with MicStream(CONFIG) as mic:
        while True:
            try:
                print("Listening...")
                audio = mic.listen()
                if audio is None:
                    print("(transient noise/click discarded)\n")
                    continue
                text, lang = stt.transcribe(audio)
                print(f"Transcript [{lang}]: {text}\n")
            except KeyboardInterrupt:
                break
