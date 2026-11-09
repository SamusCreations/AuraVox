"""
Turns a long recording into the reference of a cloned voice.

Qwen3-TTS's in-context prompt (reference codes + their transcript) gets
slower with its length and adds little past ~20 s, so a long audio is not
fed whole. Instead:

- Whisper (with its VAD) splits it into phrases with word timestamps. Bad
  phrases are dropped: uncertain transcription, noisy, clipped or too fast.
- The best ones, up to REF_SECONDS, become the voice's reference
  (custom_voices/<id>.wav + ref_text): whole phrases, in their original
  order, at a matched volume.
- All the phrases that passed (custom_voices/<id>.full.wav) are used by the
  worker to average the speaker embedding (timbre) over much more speech.

Decisions come from measurements (Whisper's confidence, signal-to-noise,
clipping, timing), so they work the same in every language.
"""
import re

import numpy as np

SR = 24000
SR_STT = 16000
MIN_SECONDS = 3.0
MAX_SOURCE_SECONDS = 600.0     # what is analysed of a longer recording
REF_SECONDS = 20.0             # in-context reference
FULL_SECONDS = 300.0           # speech kept for the speaker embedding
PHRASE_SECONDS = (1.0, 12.0)
JOIN_GAP = 0.2
TARGET_RMS = 10 ** (-20 / 20)  # -20 dBFS
MAX_GAIN = 10 ** (9 / 20)
_SENTENCE_END = re.compile(r"[.!?…。！？;:]$")


def _rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def noise_floor(audio) -> float:
    """Typical level of the quietest parts (RMS of 30 ms frames, 10th percentile)."""
    n = int(0.03 * SR_STT)
    usable = len(audio) // n
    if not usable:
        return 1e-4
    frames = audio[: usable * n].reshape(usable, n)
    levels = np.sqrt(np.mean(np.square(frames), axis=1))
    return max(float(np.percentile(levels, 10)), 1e-5)


def phrases(segments: list) -> list:
    """Whisper segments → phrases: words up to a sentence end or a pause."""
    words = [w for seg in segments for w in seg.get("words") or [] if str(w["word"]).strip()]
    out, current = [], []

    def close():
        if current:
            out.append({"start": current[0]["start"], "end": current[-1]["end"],
                        "text": "".join(w["word"] for w in current).strip(),
                        "prob": float(np.mean([w["probability"] for w in current])), "words": len(current)})
            current.clear()

    for i, w in enumerate(words):
        current.append(w)
        next_start = words[i + 1]["start"] if i + 1 < len(words) else None
        pause = next_start is not None and next_start - w["end"] >= 0.5
        long_enough = w["end"] - current[0]["start"] >= PHRASE_SECONDS[1]
        if _SENTENCE_END.search(str(w["word"]).strip()) or pause or long_enough:
            close()
    close()
    return out


def score(phrase: dict, audio16, noise: float):
    """Quality of a phrase (higher is better), or None if it must not be used."""
    duration = phrase["end"] - phrase["start"]
    if not PHRASE_SECONDS[0] <= duration <= PHRASE_SECONDS[1] + 1:
        return None
    if phrase["prob"] < 0.55 or not 1.0 <= phrase["words"] / duration <= 6.5:
        return None
    clip = audio16[int(phrase["start"] * SR_STT):int(phrase["end"] * SR_STT)]
    if not len(clip) or np.mean(np.abs(clip) >= 0.99) > 0.005:
        return None
    snr = 20 * np.log10(max(_rms(clip), 1e-6) / noise)
    if snr < 12:
        return None
    # Whole sentences of medium length read best as the model's example.
    whole = bool(_SENTENCE_END.search(phrase["text"]))
    return float(phrase["prob"] + 0.1 * min(snr / 40, 1.0) + (0.1 if whole else 0.0) + (0.05 if 2.5 <= duration <= 9 else 0.0))


def _cut(audio, phrase: dict):
    """The phrase at 24 kHz with a little margin, short fades and matched volume."""
    start = max(0, int((phrase["start"] - 0.06) * SR))
    end = min(len(audio), int((phrase["end"] + 0.12) * SR))
    clip = audio[start:end].copy()
    fade = min(int(0.01 * SR), len(clip) // 2)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        clip[:fade] *= ramp
        clip[-fade:] *= ramp[::-1]
    return clip * min(TARGET_RMS / max(_rms(clip), 1e-6), MAX_GAIN)


def _join(clips: list):
    gap = np.zeros(int(JOIN_GAP * SR), dtype=np.float32)
    parts = []
    for clip in clips:
        parts += [clip, gap]
    joined = np.concatenate(parts[:-1])
    peak = float(np.max(np.abs(joined))) if len(joined) else 0.0
    return joined * (0.89 / peak) if peak > 0.89 else joined


def build(audio24, audio16, segments: list) -> dict:
    """{"ref": audio, "ref_text", "full": audio or None, "phrases", "used", "seconds"}.
    Audio with no usable phrase falls back to its start, whole."""
    seconds = len(audio24) / SR
    noise = noise_floor(audio16)
    scored = []
    for p in phrases(segments):
        s = score(p, audio16, noise)
        if s is not None:
            scored.append({**p, "score": s})
    ranked, chosen, total = sorted(scored, key=lambda p: -p["score"]), [], 0.0
    for p in ranked:
        length = p["end"] - p["start"]
        if total + length > REF_SECONDS + 2:
            continue
        chosen.append(p)
        total += length
        if total >= REF_SECONDS:
            break
    if total < MIN_SECONDS:
        head = audio24[: int(REF_SECONDS * SR)]
        gain = min(TARGET_RMS / max(_rms(head), 1e-6), MAX_GAIN)
        head = np.clip(head * gain, -0.89, 0.89)
        text = " ".join(str(s["text"]).strip() for s in segments if s["start"] < REF_SECONDS).strip()
        return {"ref": head, "ref_text": text, "full": None, "phrases": 0, "used": len(head) / SR, "seconds": seconds}
    chosen.sort(key=lambda p: p["start"])
    ref = _join([_cut(audio24, p) for p in chosen])
    full_clips, full_total = [], 0.0
    # Best phrases first when there is more speech than what is kept.
    for p in sorted(ranked[:], key=lambda p: -p["score"]):
        if full_total >= FULL_SECONDS:
            break
        full_clips.append(p)
        full_total += p["end"] - p["start"]
    full_clips.sort(key=lambda p: p["start"])
    full = _join([_cut(audio24, p) for p in full_clips]) if full_total > total + 1 else None
    return {"ref": ref, "ref_text": " ".join(p["text"] for p in chosen), "full": full, "phrases": len(chosen),
            "used": len(ref) / SR, "seconds": seconds}
