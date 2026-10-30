"""
Micrófono abierto de forma CONTINUA para voice_loop.py y la escucha manos
libres de la interfaz web (webui/voice_listener.py), con un VAD simple por
energía (RMS) para separar las frases habladas.

Antes cada frase abría un stream de audio nuevo y medía el ruido ambiente
durante 0,5 s antes de escuchar: lo que se decía en ese medio segundo (o
entre un stream y el siguiente, p. ej. justo después del pitido) se perdía,
y si se empezaba a hablar durante la medición el umbral subía. Ahora el
stream queda abierto, los bloques se acumulan en una cola y el ruido
ambiente se sigue midiendo solo con los bloques en silencio (se congela
mientras el asistente habla, para no medir su propia voz como ruido).

    mic = MicStream(stt_whisper.CONFIG)
    mic.open()
    audio = mic.listen(timeout=5)   # numpy float32 mono, None o Interrupted
"""
import collections
import threading

import numpy as np
import sounddevice as sd


class Interrupted:
    """Lo que devuelve listen() si `interrupt()` devolvió algo (p. ej. el
    asistente cuya tecla de push to talk se apretó) — `value` es ese algo."""

    def __init__(self, value):
        self.value = value


def _rms(block) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))


class MicStream:
    # Audio de antes del arranque de la frase que se agrega al principio:
    # el VAD arranca cuando la voz ya sube, y sin esto se comía la primera
    # consonante ("Jarvis" → "arvis").
    PREROLL_SECONDS = 0.3
    # Lo que se guarda como máximo sin que nadie lo lea (p. ej. mientras el
    # modelo piensa): lo más viejo se descarta.
    BACKLOG_SECONDS = 60.0
    # Qué tan rápido sigue el ruido ambiente a los bloques en silencio.
    NOISE_SMOOTHING = 0.03

    def __init__(self, config: dict):
        self.cfg = config
        self.block_size = int(config["samplerate"] * config["block_ms"] / 1000)
        self.block_seconds = config["block_ms"] / 1000
        self._blocks = collections.deque(maxlen=int(self.BACKLOG_SECONDS / self.block_seconds))
        self._cond = threading.Condition()
        self._stream = None
        self.noise = None
        self._frozen = False

    # ── Ciclo de vida ──────────────────────────────────────────────────
    def open(self) -> None:
        if self._stream is not None:
            return
        stream = sd.InputStream(
            samplerate=self.cfg["samplerate"],
            channels=1,
            dtype="float32",
            blocksize=self.block_size,
            device=self.cfg["device_index"],
            callback=self._callback,
        )
        stream.start()
        self._stream = stream
        if self.noise is None:
            self.calibrate()

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            for op in (stream.stop, stream.close):
                try:
                    op()
                except sd.PortAudioError:
                    pass
        with self._cond:
            self._blocks.clear()
            self._cond.notify_all()

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def _callback(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        with self._cond:
            self._blocks.append(block)
            self._cond.notify()

    def _read(self, timeout: float = 1.0):
        with self._cond:
            if not self._blocks and self._stream is not None:
                self._cond.wait(timeout)
            return self._blocks.popleft() if self._blocks else None

    def flush(self) -> None:
        """Descarta lo que se grabó y nadie leyó todavía (el pitido, lo que
        sonó mientras el modelo pensaba...)."""
        with self._cond:
            self._blocks.clear()

    # ── Ruido ambiente ─────────────────────────────────────────────────
    @property
    def threshold(self) -> float:
        noise = self.noise or 0.0
        return max(noise * self.cfg["threshold_multiplier"], self.cfg["min_threshold"])

    def calibrate(self, seconds: float = None) -> None:
        """Mide el ruido ambiente (solo hace falta al abrir: después se va
        siguiendo solo con los bloques en silencio)."""
        n = max(1, int((seconds or self.cfg["calibration_seconds"]) / self.block_seconds))
        levels = []
        while len(levels) < n:
            block = self._read()
            if block is None:
                break
            levels.append(_rms(block))
        if levels:
            self.noise = sum(levels) / len(levels)

    def freeze_noise(self, frozen: bool = True) -> None:
        """Mientras el asistente habla, el altavoz no es ruido ambiente: si
        se midiera, el umbral subiría y costaría más interrumpirlo."""
        self._frozen = frozen

    def _track_noise(self, rms: float) -> None:
        if self._frozen or self.noise is None:
            return
        self.noise += (rms - self.noise) * self.NOISE_SMOOTHING

    # ── Captura ────────────────────────────────────────────────────────
    def listen(self, timeout: float = None, interrupt=None, silence_timeout: float = None, on_start=None):
        """Espera una frase hablada y la devuelve (numpy float32 mono), o
        None si pasaron `timeout` segundos sin voz (o fue un ruido suelto).

        `interrupt`, si se pasa, se consulta en cada bloque (~30 ms) mientras
        todavía no empezó una frase: si devuelve algo verdadero, se devuelve
        `Interrupted(ese_valor)` (push to talk, silenciar el micrófono...).
        `on_start()` se llama cuando arranca la frase (para mostrar "te
        escucho"). La frase termina tras `silence_timeout` segundos de
        silencio (por defecto el de la configuración)."""
        cfg = self.cfg
        bs = self.block_seconds
        silence_timeout = silence_timeout or cfg["silence_timeout"]
        max_blocks = int(cfg["max_utterance_seconds"] / bs)
        preroll = collections.deque(maxlen=max(1, int(self.PREROLL_SECONDS / bs)))
        recorded, levels = [], []
        started = False
        voiced = 0
        silence = waited = 0.0

        while True:
            if interrupt is not None and not started:
                value = interrupt()
                if value:
                    return Interrupted(value)
            block = self._read()
            if block is None:
                if self._stream is None:
                    return None  # se cerró el micrófono
                waited += 1.0
                if timeout is not None and not started and waited >= timeout:
                    return None
                continue
            rms = _rms(block)
            threshold = self.threshold

            if not started:
                if rms >= threshold:
                    started = True
                    recorded.extend(preroll)
                    recorded.append(block)
                    levels.append(rms)
                    voiced = 1
                    if on_start:
                        on_start()
                else:
                    self._track_noise(rms)
                    preroll.append(block)
                    waited += bs
                    if timeout is not None and waited >= timeout:
                        return None
                continue

            recorded.append(block)
            levels.append(rms)
            if rms < threshold:
                silence += bs
            else:
                silence = 0.0
                voiced += 1
            if silence >= silence_timeout or len(recorded) >= max_blocks:
                break

        if len(recorded) >= max_blocks and not self._frozen:
            # Una "frase" de 25 s sin ningún silencio suele ser que subió el
            # ruido de fondo (un ventilador): se toma lo más bajo de lo
            # grabado como el ruido nuevo.
            self.noise = max(self.noise or 0.0, float(np.percentile(levels, 20)))
        if voiced * bs < cfg["min_voiced_seconds"]:
            return None  # un golpe o click suelto, no habla
        return np.concatenate(recorded).reshape(-1)

    def record_while(self, keep_going, max_seconds: float = 30.0, tail_seconds: float = 0.25):
        """Graba mientras `keep_going()` sea verdadero (push to talk), más
        una colita de `tail_seconds` para no cortar la última sílaba.
        Devuelve el audio, o None si fue un toque demasiado corto."""
        bs = self.block_seconds
        blocks = []
        released = elapsed = 0.0
        while elapsed < max_seconds:
            block = self._read()
            if block is None:
                if self._stream is None:
                    break
                continue
            blocks.append(block)
            elapsed += bs
            if keep_going():
                released = 0.0
            else:
                released += bs
                if released >= tail_seconds:
                    break
        if not blocks or elapsed - released < self.cfg["min_speech_seconds"]:
            return None
        return np.concatenate(blocks).reshape(-1)
