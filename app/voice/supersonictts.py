"""
SupersonicTTS - motor de voz para Jarvis.
Usa Supertonic (Supertone Inc.), un TTS multilenguaje on-device basado en
ONNX Runtime: rápido, ligero y 100% local tras la primera descarga del
modelo desde Hugging Face.

Uso:
    from app.voice.supersonictts import JarvisVoice
    voz = JarvisVoice()
    voz.speak("Hola, soy JARVIS.", "salida.wav")

Ejecutado directamente (`python supersonictts.py`) hace una prueba y abre un
modo interactivo para escribir texto y escuchar el resultado.
"""
import os
import re
import sys
import threading
import time

# La consola de Windows suele usar cp1252, que no soporta los emojis de los
# mensajes de progreso; forzamos utf-8 para evitar UnicodeEncodeError.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from num2words import num2words

# Ejecutado como script (los .bat): la raíz del proyecto va al path para
# poder importar el paquete `app` (el Python embebido no lo agrega solo).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.voice import cuda_setup  # noqa: E402

import supertonic.loader as _supertonic_loader  # noqa: E402
from supertonic import TTS  # noqa: E402
from supertonic.config import AVAILABLE_LANGUAGES  # noqa: E402

# Supertonic ya filtra internamente los emoji "normales" (😊, 🌿...), pero los
# selectores de variación (p.ej. el ️ invisible que acompaña a ☀️, ✨, ✅...)
# se validan carácter por carácter y no forman parte de esa limpieza, así que
# si el LLM los genera, synthesize() lanza ValueError. Los quitamos aquí antes
# de sintetizar para que un asistente de voz nunca se caiga por esto.
_VARIATION_SELECTORS_RE = re.compile("[\U0000FE00-\U0000FE0F\U000E0100-\U000E01EF]")

# El LLM normalmente ya escribe los números en palabras, pero cuando cita algo textual de una búsqueda (un precio, un
# año, un porcentaje) a veces se cuela un número en dígitos, y Supertonic
# los lee mal (los deletrea dígito por dígito en vez de decir la cifra).
# Esto los convierte a palabras antes de sintetizar. `num2words` no cubre
# los 31 idiomas de Supertonic-3 (le faltan bg, el, et, hi, hr); para esos
# los números se dejan tal cual en vez de fallar.
_NUM2WORDS_LANGS = {
    "ar", "cs", "da", "de", "en", "es", "fi", "fr", "hu", "id", "it", "ja",
    "ko", "lt", "lv", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr",
    "uk", "vi",
}
_NUMBER_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")

# num2words lee el decimal en español siempre como "punto" ("27,5" →
# "veintisiete punto cinco"), pero quien escribe "27,5" dice "coma". Para
# estos idiomas se arma la lectura a mano con la palabra del separador que
# de verdad se usó; el resto de idiomas ya usa su palabra correcta en
# num2words ("Komma", "virgule"...).
_DECIMAL_WORDS = {"es": {",": "coma", ".": "punto"}}


def _valid_thousands(groups: list) -> bool:
    return 1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:])


def _split_number(raw: str):
    """Separa `raw` en (parte_entera, separador_decimal, decimales),
    distinguiendo el separador de miles del decimal — sin esto "1.500"
    (mil quinientos, como se escribe en español) se leía "uno punto cinco".

    - Con "." y "," a la vez, el último es el decimal ("1.234,5", "1,234.5").
    - Un separador repetido siempre es de miles ("1.500.000", "1,500,000").
    - Un separador único seguido de exactamente 3 dígitos es de miles
      ("1.500", "2,000"): un decimal de justo 3 cifras es rarísimo en habla
      y los miles son muy comunes (precios, habitantes, distancias).
    - Si no, es decimal ("27,5", "3.14").

    Devuelve None si no tiene forma de número (p. ej. "3.10.2", una
    versión): se deja tal cual."""
    seps = [c for c in raw if c in ".,"]
    if not seps:
        return raw, None, None
    if len(set(seps)) == 2:
        dec = seps[-1]
        if raw.count(dec) != 1:
            return None
        int_str, frac = raw.rsplit(dec, 1)
        groups = int_str.split(seps[0])
        return ("".join(groups), dec, frac) if _valid_thousands(groups) else None
    groups = re.split(r"[.,]", raw)
    if len(seps) > 1:
        return ("".join(groups), None, None) if _valid_thousands(groups) else None
    int_str, frac = groups
    if len(frac) == 3 and len(int_str) <= 3 and int_str != "0":
        return int_str + frac, None, None
    return int_str, seps[0], frac


def _number_to_words(raw: str, lang: str) -> str:
    parts = _split_number(raw)
    if parts is None:
        return raw
    int_str, sep, frac = parts
    int_words = num2words(int(int_str), lang=lang)
    if not frac or int(frac) == 0:
        return int_words
    sep_word = _DECIMAL_WORDS.get(lang, {}).get(sep)
    if not sep_word:
        return num2words(float(f"{int_str}.{frac}"), lang=lang)
    # "3,05" → "tres coma cero cinco": los ceros iniciales se dicen uno a uno.
    zeros = len(frac) - len(frac.lstrip("0"))
    frac_words = [num2words(0, lang=lang)] * zeros + [num2words(int(frac), lang=lang)]
    return f"{int_words} {sep_word} {' '.join(frac_words)}"


# Símbolos y unidades que el LLM copia de las búsquedas ("24°C", "30 %",
# "15 km/h") y que Supertonic no sabe leer: se escriben como se dicen antes
# de pasar los números a palabras. Bug real: "rondan los 24°C" sonaba raro.
_UNITS = {
    "es": [
        (r"°\s*C\b", " grados"), (r"°\s*F\b", " grados Fahrenheit"), (r"°", " grados"),
        (r"\s*%", " por ciento"), (r"\s*km/h\b", " kilómetros por hora"), (r"\s*km\b", " kilómetros"),
        (r"\s*mm\b", " milímetros"), (r"\s*cm\b", " centímetros"), (r"\s*kg\b", " kilos"), (r"\s*m\b(?![/²³])", " metros"),
    ],
    "en": [
        (r"°\s*C\b", " degrees Celsius"), (r"°\s*F\b", " degrees Fahrenheit"), (r"°", " degrees"),
        (r"\s*%", " percent"), (r"\s*km/h\b", " kilometers per hour"), (r"\s*mph\b", " miles per hour"),
        (r"\s*km\b", " kilometers"), (r"\s*mm\b", " millimeters"), (r"\s*cm\b", " centimeters"), (r"\s*kg\b", " kilograms"),
    ],
}
_UNITS_RE = {
    lang: [(re.compile(r"(?<=\d)" + pattern), words) for pattern, words in rules]
    for lang, rules in _UNITS.items()
}

# Horas "7:19", "7:19 p. m.", "19:05", "7:05 PM". Sin esto "7:19" se leía
# "siete:diecinueve" (el ":" no se pronuncia) y "p. m." quedaba a la suerte.
_TIME_RE = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])(?:\s*([ap])\.?\s?m\b\.?)?", re.I)


def _say_time(match: re.Match, lang: str) -> str:
    hour, minute = int(match.group(1)), int(match.group(2))
    suffix = (match.group(3) or "").lower()
    if hour > 24 or minute > 59:
        return match.group(0)
    if lang == "es":
        words = "una" if hour == 1 else num2words(hour, lang="es")
        if minute:
            words += f" y {num2words(minute, lang='es')}"
        elif not suffix:
            words += " en punto"
        if suffix:
            words += " a eme" if suffix == "a" else " pe eme"
        return words
    if lang == "en":
        words = num2words(hour, lang="en")
        if minute:
            words += f" oh {num2words(minute, lang='en')}" if minute < 10 else f" {num2words(minute, lang='en')}"
        elif not suffix:
            words += " o'clock"
        if suffix:
            words += " A M" if suffix == "a" else " P M"
        return words
    return f"{match.group(1)} {match.group(2)}"  # otros idiomas: al menos sin el ":"


def _normalize_for_speech(text: str, lang: str) -> str:
    text = _TIME_RE.sub(lambda m: _say_time(m, lang), text)
    for pattern, words in _UNITS_RE.get(lang, []):  # solo es/en; en otros idiomas se deja tal cual
        text = pattern.sub(words, text)
    return text


def _numbers_to_words(text: str, lang: str) -> str:
    text = _normalize_for_speech(text, lang)
    if lang not in _NUM2WORDS_LANGS:
        return text

    def _replace(match: re.Match) -> str:
        raw = match.group(0)
        try:
            return _number_to_words(raw, lang)
        except (ValueError, NotImplementedError, OverflowError):
            return raw  # algo que no se pudo convertir: se deja tal cual, no se rompe la síntesis

    return _NUMBER_RE.sub(_replace, text)

# ══════════════════════════════════════════════════════════════════════
# PLANTILLA DE PARÁMETROS — edita estos valores cuando quieras
# ══════════════════════════════════════════════════════════════════════
CONFIG = {
    # Modelo Supertonic a usar: "supertonic", "supertonic-2" o "supertonic-3"
    # (el más reciente y con mejor calidad/precisión de lectura).
    "model": "supertonic-3",

    # Carpeta donde se guarda/busca el modelo descargado de Hugging Face.
    # None = usa la caché por defecto de huggingface_hub.
    "model_dir": None,

    # Voz preentrenada. Supertonic-3 trae 10 voces: M1..M5 (masculinas) y
    # F1..F5 (femeninas). M5 es la voz por defecto de este módulo; cada
    # asistente la cambia por la suya (`voice` en assistants.yaml).
    "voice": "M5",

    # Idioma de síntesis por defecto (código ISO 639-1), usado cuando
    # `speak()` no recibe un `lang` explícito por llamada (p. ej. los
    # anuncios cortos fijos de voice_loop.py, o el modo texto). Supertonic-3
    # es multilenguaje (ver AVAILABLE_LANGUAGES); voice_loop.py le pasa el
    # idioma detectado por Whisper en cada turno para que la voz responda en
    # el mismo idioma en el que le hablaron.
    "language": "es",

    # ── Síntesis ──
    "total_steps": 8,        # pasos de difusión: más = más calidad, más lento
    "speed": 1.0,            # multiplicador de velocidad del habla
    "silence_duration": 0.3,  # segundos de silencio entre trozos de texto largo
}
# ══════════════════════════════════════════════════════════════════════


def create_tts(cfg: dict = None):
    """Crea el modelo Supertonic en GPU si se puede (ver cuda_setup) y
    devuelve (modelo, dispositivo, motivo). Supertonic trae la CPU fija en
    supertonic.config; se cambia la lista de proveedores que lee su loader
    justo antes de crear las sesiones ONNX."""
    cfg = cfg or CONFIG
    providers, reason = cuda_setup.onnx_providers()
    _supertonic_loader.DEFAULT_ONNX_PROVIDERS = providers
    model = TTS(model=cfg["model"], model_dir=cfg["model_dir"], auto_download=True)
    sessions = [v for v in vars(model.model).values() if hasattr(v, "get_providers")]
    device = cuda_setup.session_device(sessions)
    if device == "CPU" and "CUDAExecutionProvider" in providers:
        reason = "CPU: onnxruntime could not initialize CUDA (check messages above)"
    return model, device, reason


# UN solo modelo Supertonic por proceso, compartido por todas las voces:
# antes voice_loop.py cargaba uno por asistente (dos copias iguales en
# memoria/VRAM para JARVIS y BELLA) cuando lo único que cambia entre voces
# es el estilo (get_voice_style). SYNTH_LOCK serializa las síntesis porque
# todas usan las mismas sesiones ONNX.
_shared = {"key": None, "model": None, "device": "", "reason": ""}
_shared_lock = threading.Lock()
SYNTH_LOCK = threading.Lock()


def shared_tts(cfg: dict = None):
    """(modelo, dispositivo, motivo) del modelo compartido; lo carga la
    primera vez (o si se pide otro modelo/carpeta)."""
    cfg = cfg or CONFIG
    key = (cfg["model"], cfg["model_dir"])
    with _shared_lock:
        if _shared["model"] is None or _shared["key"] != key:
            print(f"Loading Supertonic model ({cfg['model']}) ...")
            t0 = time.time()
            model, device, reason = create_tts(cfg)
            _shared.update(key=key, model=model, device=device, reason=reason)
            print(f"Model loaded in {time.time() - t0:.1f}s — {reason}\n")
        return _shared["model"], _shared["device"], _shared["reason"]


def release_shared_tts() -> bool:
    """Suelta el modelo compartido (para liberar memoria). True si había uno."""
    with _shared_lock:
        had = _shared["model"] is not None
        _shared.update(key=None, model=None, device="", reason="")
        return had


class JarvisVoice:
    """Una voz (estilo + velocidad) sobre el modelo Supertonic compartido."""

    def __init__(self, config: dict = None):
        self.config = config or CONFIG
        self._model = None
        self._style = None

    def _load(self):
        model, _device, _reason = shared_tts(self.config)
        if self._model is not model:
            self._model = model
            self._style = model.get_voice_style(self.config["voice"])
        return self._model

    def release(self) -> None:
        """Olvida el modelo y el estilo (el modelo en sí se suelta con
        release_shared_tts())."""
        self._model = None
        self._style = None

    def speak(self, text: str, out_path: str = "salida.wav", lang: str = None) -> str:
        """`lang`: código ISO 639-1 para esta síntesis (p. ej. "en"). Si no se
        pasa, usa `cfg["language"]`. Si el código no está entre los idiomas
        que soporta el modelo (`AVAILABLE_LANGUAGES`), cae a "na" (idioma
        desconocido/no soportado) en vez de fallar."""
        model = self._load()
        cfg = self.config
        text = _VARIATION_SELECTORS_RE.sub("", text)

        lang = lang or cfg["language"]
        if lang not in AVAILABLE_LANGUAGES:
            lang = "na"

        text = _numbers_to_words(text, lang)

        with SYNTH_LOCK:
            t0 = time.time()
            wav, _ = model.synthesize(
                text=text,
                voice_style=self._style,
                total_steps=cfg["total_steps"],
                speed=cfg["speed"],
                silence_duration=cfg["silence_duration"],
                lang=lang,
            )
            dur = time.time() - t0
        model.save_audio(wav, out_path)
        audio_seg = wav.shape[-1] / 44100
        rtf = dur / audio_seg if audio_seg else 0.0
        print(f"⏱  {dur:.2f}s for {audio_seg:.1f}s of audio  (RTF {rtf:.2f}x) → {out_path}")
        return out_path


if __name__ == "__main__":
    jarvis_voice = JarvisVoice()
    jarvis_voice.speak("Hola, soy JARVIS y estoy aquí para ayudarte en lo que necesites.", "test1.wav")
    jarvis_voice.speak("Esta es la segunda generación para medir la velocidad real.", "test2.wav")

    print("\nType text to synthesize (or 'exit'):")
    while True:
        txt = input("> ").strip()
        if txt.lower() in ("salir", "exit", "quit", ""):
            break
        jarvis_voice.speak(txt, "interactivo.wav")
