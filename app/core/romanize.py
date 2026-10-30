"""
Transliteración aproximada al alfabeto latino, sin dependencias, para
COMPARAR NOMBRES (palabras de activación, asistentes nombrados en una
frase) en los 31 idiomas del pipeline.

Por qué hace falta: Whisper escribe el nombre con el alfabeto del idioma en
que se habló — "Джарвис" (ruso), "Τζάρβις" (griego), "جارفيس" (árabe),
"जार्विस" (hindi), "ジャービス" (japonés), "자비스" (coreano) — y la
coincidencia difusa contra "jarvis" daba 0. Con esto queda "jarvis",
"jarvis", "jarfis", "jarvis", "jabisu", "jabis": lo bastante parecido para
el umbral de wake_word_utils.

No es una romanización académica (no hace falta): solo tiene que dejar
parecido lo que suena parecido. Los idiomas con alfabeto latino ya se
resuelven quitando las tildes (ver wake_word_utils.normalize); aquí además
se cubren las letras que no se descomponen (ł, ø, ß, đ, ı...). Los kanji/
hanzi se dejan tal cual.
"""
import re
import unicodedata

# ── Cirílico (ruso, ucraniano, búlgaro) ────────────────────────────────
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "ё": "e", "є": "ye",
    "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh",
    "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}
# "Дж" es como se escribe la J inglesa (Джарвис = Jarvis).
_CYRILLIC_DIGRAPHS = {"дж": "j"}

# ── Griego ─────────────────────────────────────────────────────────────
_GREEK = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i",
    "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}
# Cómo se escriben en griego la b, la d, la j y la g de otros idiomas
# (Μπέλλα = Bella, Τζάρβις = Jarvis).
_GREEK_DIGRAPHS = {"μπ": "b", "ντ": "d", "τζ": "j", "γκ": "g", "ου": "u"}

# ── Árabe (las vocales cortas son marcas y se descartan) ───────────────
_ARABIC = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h",
    "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "و": "u", "ي": "i", "ى": "a", "ة": "a", "ء": "", "ئ": "i", "ؤ": "u",
    "پ": "p", "ڤ": "v", "گ": "g", "چ": "ch",
}

# ── Devanagari (hindi) ─────────────────────────────────────────────────
_DEVA_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_DEVA_VOWELS = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o",
    "औ": "au", "ऋ": "ri",
}
_DEVA_SIGNS = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ृ": "ri",
}
_DEVA_VIRAMA = "्"
_DEVA_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}
_DEVA_NUKTA = "़"

# ── Kana (japonés), Hepburn simplificado ───────────────────────────────
_KANA = dict(zip(
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
    "がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゔ",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho "
    "ma mi mu me mo ya yu yo ra ri ru re ro wa o n ga gi gu ge go za ji zu ze zo da ji zu de do "
    "ba bi bu be bo pa pi pu pe po vu".split(),
))
_SMALL_Y = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
_SMALL_VOWEL = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}

# ── Hangul (coreano), romanización revisada simplificada ───────────────
_HANGUL_L = "g kk n d tt r m b pp s ss _ j jj ch k t p h".split()
_HANGUL_V = "a ae ya yae eo e yeo ye o wa wae oe yo u wo we wi yu eu ui i".split()
_HANGUL_T = [""] + "g kk gs n nj nh d l lg lm lb ls lt lp lh m b bs s ss ng j ch k t p h".split()

# Letras latinas que NFD no descompone (no son "letra + tilde").
_LATIN_EXTRA = {
    "ł": "l", "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ð": "d", "þ": "th", "ı": "i",
    "ŀ": "l", "ħ": "h",
}


def _hangul(ch: str) -> str:
    s = ord(ch) - 0xAC00
    lead, vowel, tail = s // 588, (s % 588) // 28, s % 28
    first = "" if _HANGUL_L[lead] == "_" else _HANGUL_L[lead]
    # 스, 크, 트… sin consonante final: la "eu" es la vocal de apoyo de los
    # préstamos (자비스 = ja-bi-s), no se pronuncia como sílaba plena.
    if vowel == 18 and tail == 0:
        return first
    return first + _HANGUL_V[vowel] + _HANGUL_T[tail]


def _kana(text: str) -> str:
    out = []
    double_next = False
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:  # katakana → hiragana
            ch = chr(code - 0x60)
        if ch == "っ":
            double_next = True
            continue
        if ch in ("ー", "・"):
            continue
        if ch in _SMALL_Y and out:
            prev = out[-1]
            # ki+ya → kya; shi+ya → sha; chi+ya → cha; ji+ya → ja
            if prev.endswith(("shi", "chi", "ji")):
                out[-1] = prev[:-1] + _SMALL_Y[ch]
            else:
                out[-1] = prev[:-1] + "y" + _SMALL_Y[ch]
            continue
        if ch in _SMALL_VOWEL and out:
            # ヴァ → va, フィ → fi, ティ → ti (sonidos de préstamos)
            prev = out[-1]
            out[-1] = (prev[:-1] if len(prev) > 1 else prev) + _SMALL_VOWEL[ch]
            continue
        roman = _KANA.get(ch)
        if roman is None:
            out.append(ch)
            continue
        if double_next and roman[0] not in "aeioun":
            roman = roman[0] + roman
        double_next = False
        out.append(roman)
    return "".join(out)


def _devanagari(text: str) -> str:
    out = []
    pending_a = False  # la consonante anterior lleva su "a" implícita

    def close_word():
        nonlocal pending_a
        pending_a = False  # la "a" final no se pronuncia en hindi (जार्विस = jarvis)

    for ch in text:
        if ch in _DEVA_CONSONANTS:
            if pending_a:
                out.append("a")
            out.append(_DEVA_CONSONANTS[ch])
            pending_a = True
        elif ch in _DEVA_SIGNS:
            out.append(_DEVA_SIGNS[ch])
            pending_a = False
        elif ch == _DEVA_VIRAMA:
            pending_a = False
        elif ch == _DEVA_NUKTA:
            continue
        elif ch in _DEVA_NASAL:
            if pending_a:
                out.append("a")
                pending_a = False
            out.append(_DEVA_NASAL[ch])
        elif ch in _DEVA_VOWELS:
            if pending_a:
                out.append("a")
                pending_a = False
            out.append(_DEVA_VOWELS[ch])
        else:
            close_word()
            out.append(ch)
    close_word()
    return "".join(out)


_KANA_RE = re.compile(r"[ぁ-ゟ゠-ヿ]+")
_DEVA_RE = re.compile(r"[ऀ-ॿ]+")
_HANGUL_RE = re.compile(r"[가-힣]")


def _digraphs(text: str, table: dict) -> str:
    for src, dst in table.items():
        text = text.replace(src, dst)
    return text


def romanize(text: str) -> str:
    """`text` en minúsculas con los alfabetos no latinos pasados a letras
    latinas (aproximado, ver arriba). Lo que ya es latino queda igual,
    salvo las letras de _LATIN_EXTRA."""
    text = unicodedata.normalize("NFC", text.lower())
    if _KANA_RE.search(text):
        text = _KANA_RE.sub(lambda m: _kana(m.group(0)), text)
    if _DEVA_RE.search(text):
        text = _DEVA_RE.sub(lambda m: _devanagari(m.group(0)), text)
    if _HANGUL_RE.search(text):
        text = _HANGUL_RE.sub(lambda m: _hangul(m.group(0)), text)
    # Sin tildes ni marcas: "ά" → "α", "й" → "и", vocales cortas del árabe.
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = _digraphs(text, _CYRILLIC_DIGRAPHS)
    text = _digraphs(text, _GREEK_DIGRAPHS)
    return "".join(
        _CYRILLIC.get(c) if c in _CYRILLIC
        else _GREEK.get(c) if c in _GREEK
        else _ARABIC.get(c) if c in _ARABIC
        else _LATIN_EXTRA.get(c, c)
        for c in text
    )
