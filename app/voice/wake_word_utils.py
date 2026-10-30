"""
Palabra de activación: lectura/escritura de wake_words.txt y la
coincidencia difusa que usa voice_loop.py para reconocer el nombre de cada
asistente pese a errores de transcripción de Whisper.

Vive aparte de voice_loop.py para que la interfaz web (config_ui.py) pueda
usar exactamente la misma lógica — p. ej. para avisar qué palabras comunes
activarían por error a un asistente nuevo — sin importar voice_loop.py
(que carga Whisper y las voces al importarse).

wake_words.txt tiene una sección por asistente ("[jarvis]", "[bella]"...)
con variantes/apodos que cuentan como su nombre, y una sección especial
"[excluir]" con palabras comunes que NUNCA cuentan como coincidencia
aproximada de ningún nombre. Bug real que motivó "[excluir]":
SequenceMatcher("ella", "bella") da 0.89, muy por encima del umbral, así
que cualquier frase que empezara con "ella..." despertaba a BELLA.
"""
import difflib
import os
import re

from app.core.romanize import romanize
from app.paths import WAKE_WORDS_TXT as WAKE_WORDS_PATH

# Sección especial de wake_words.txt (no es un asistente).
EXCLUDE_SECTION = "excluir"

# Umbral de similitud (0-1) para reconocer el nombre pese a errores de
# transcripción de Whisper (p. ej. "harvis", "yarvis", "vella", "beya"...).
# voice_loop.py lo usa como CONFIG["wake_word_ratio"].
DEFAULT_RATIO = 0.62

# Palabras frecuentes (español e inglés, sin tildes) contra las que la
# interfaz web revisa si el nombre/alias de un asistente se activaría por
# error. No afecta al reconocimiento en sí: solo sirve para AVISAR y
# sugerir agregarlas a "[excluir]".
COMMON_WORDS = sorted(set("""
de la que el en y a los se del las un por con no una su para es al lo como mas o pero sus le ha me si
sin sobre este ya entre cuando todo esta ser son dos tambien fue habia era muy anos hasta desde mi
porque solo han yo hay vez puede todos asi nos ni parte tiene uno donde bien tiempo mismo ese ahora
cada vida otro despues te otros aunque esa eso hace otra dia tanto ella ellas ello elle tres dijo sido
gran pais segun menos mundo ano antes estado quiero contra sino forma caso nada hacer general estaba
poco estos mayor ante unos les algo hacia casa ellos ayer hecho primera mucho mientras ademas quien
momento esto hombre estan pues hoy lugar trabajo otras mejor nuevo decir algunos entonces todas dias
debe casi toda tal luego pasado primer medio va estas sea tenia nunca aqui ver veces partido personas
grupo cuenta pueden tienen misma nueva cual fueron mujer frente cosas fin ciudad tener sistema sera
historia muchos tipo cuatro dentro nuestro punto dice cualquier noche aun agua parece haber fuera
bajo grandes nuestra ejemplo acuerdo usted hizo nadie horas posible tarde importante sentido lado tu
cambio alli mano eran estar numero centro padre gente final cuerpo obra incluso ultimo madre mis modo
problema cinco nombre algunas publico mujeres todavia meses manana esos nosotros hora muchas pueblo
alguna dar don da derecho verdad podria seria junto cabeza aquel cuanto tierra equipo segundo dicho
cierto casos manos nivel podia familia largo partir falta llegar propio cosa primero hemos mal algun
tuvo semana varios real hija hijo bello bellos bellas belleza vela velas velo sella mella huella pella
estrella bola bala valla vaya calle bebe selva vale jarabe jardin jarra jarras jarro servis travis
marvin paris javier jaime mario marcos iris carlos maria juan jose luis ariel hola oye mira dime venga
vamos gracias bueno perfecto claro listo apaga enciende pon quita sube baja abre cierra busca llama
cuando donde como cuales hey okay oiga escucha perdon disculpa adios buenas buenos noches tardes
genial exacto
the be to of and in that have it for not on with he as you do at this but his by from they we say her
she or an will my one all would there their what so up out if about who get which go me when make can
like time no just him know take people into year your good some could them see other than then now
look only come its over think also back after use two how our work first well way even new want
because any these give day most us hello bell fella hella yellow jealous service nervous harvest
carvings marvis garbage
""".split()))


def normalize(text: str) -> str:
    """Minúsculas, sin tildes/diacríticos y en letras latinas ("Bélla" →
    "bella", "Джарвис" → "jarvis", "ジャービス" → "jabisu"): Whisper escribe
    el nombre con el alfabeto del idioma en que se habló (ver romanize.py)."""
    return romanize(text.strip())


def similarity(word: str, candidate: str) -> float:
    return 1.0 if word == candidate else difflib.SequenceMatcher(None, word, candidate).ratio()


def match_ratio(word: str, candidate: str, exclusions) -> float:
    """Parecido de `word` (ya normalizada) con `candidate` (nombre o alias)
    como lo evalúa voice_loop.py: una coincidencia EXACTA siempre cuenta
    (aunque la palabra esté en `exclusions`, así un alias explícito gana);
    una palabra excluida nunca cuenta como coincidencia aproximada."""
    if word == candidate:
        return 1.0
    if word in exclusions:
        return 0.0
    # Un error de transcripción cambia una o dos letras, no el largo de la
    # palabra: "servicios" se parecía un 67 % a "yervis" (alias de Jarvis) y
    # al final de la frase eso bastaba para tomarlo por el nombre.
    if abs(len(word) - len(candidate)) > 2:
        return 0.0
    # Nombres cortos (bella, ziggy): como mucho UNA letra cambiada, sobrante
    # o faltante. Visto: "Tell me about…" se convertía en "Bella me about…"
    # ("tell" se parece un 67 % a "bella", pero son dos cambios). Las
    # variantes escritas en wake_words.txt siguen contando tal cual (arriba).
    if len(candidate) <= 5 and _edits(word, candidate) > 1:
        return 0.0
    return difflib.SequenceMatcher(None, word, candidate).ratio()


def _edits(a: str, b: str) -> int:
    """Distancia de edición (Levenshtein) entre dos palabras cortas."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# Palabras de una frase transcrita. El katakana va aparte del resto aunque
# esté pegado (el japonés no separa palabras): "ジャービス今何時" → el nombre
# queda solo ("ジャービス") y se puede comparar. Las marcas combinantes
# (vocales del devanagari, harakat del árabe, tildes sueltas) son parte de
# la palabra aunque `\w` no las incluya: sin esto "जार्विस" se partía en letras.
_MARKS = "̀-ًͯ-ٰٟऀ-ॣ०-ॿ゙゚"
TOKEN_RE = re.compile(rf"[゠-ヿ]+|(?:[^\W゠-ヿ]|[{_MARKS}])+", re.UNICODE)

# Parecido mínimo para contar como el nombre de un asistente cuando NO está
# al principio ni al final de la frase (donde se le habla a alguien): ahí
# es más fácil que una palabra cualquiera se parezca por casualidad.
INNER_RATIO = 0.8


def tokens(text: str) -> list:
    return TOKEN_RE.findall(text or "")


def best_name(word: str, names: dict, exclusions) -> tuple:
    """(asistente, parecido) del nombre/alias más parecido a `word` (ya
    normalizada). `names`: {asistente: set(nombre y alias normalizados)}."""
    best, best_ratio = None, 0.0
    for name, candidates in names.items():
        for candidate in candidates:
            r = match_ratio(word, candidate, exclusions)
            if r > best_ratio:
                best, best_ratio = name, r
    return best, best_ratio


def find_wake_word(text: str, names: dict, exclusions, ratio: float = DEFAULT_RATIO, first: int = 3):
    """Busca el nombre de algún asistente entre las primeras `first`
    palabras de `text` (tolerando errores de transcripción). Devuelve
    (asistente, resto_del_texto) o (None, None).

    `names`: {asistente: set(nombre y variantes normalizados)} — solo los
    que se pueden llamar por su nombre. Una coincidencia EXACTA con una
    variante cuenta como parecido perfecto; las palabras de `exclusions`
    ("ella", "bello"...) nunca cuentan como parecido aproximado."""
    words = tokens(text)
    best, best_ratio, best_idx = None, 0.0, None
    for idx, word in enumerate(words[:first]):
        norm = normalize(word)
        # Una palabra de 1-2 letras se "parece" a cualquier nombre corto
        # ("va" ~ "vela" = 0.67): solo cuenta si es exactamente un alias.
        if len(norm) < 3 and not any(norm in candidates for candidates in names.values()):
            continue
        name, r = best_name(norm, names, exclusions)
        if r > best_ratio:
            best, best_ratio, best_idx = name, r, idx
    if best is None or best_ratio < ratio:
        return None, None
    # El resto: lo de antes Y lo de después del nombre. Con solo lo de
    # después, "Adiós, Ziggy" quedaba vacío y se tomaba como decir solo el
    # nombre (pitido y nada más).
    return best, " ".join(words[:best_idx] + words[best_idx + 1:]).strip()


def find_mentions(text: str, names: dict, exclusions, ratio: float = DEFAULT_RATIO, inner_ratio: float = INNER_RATIO,
                  first: int = 3) -> list:
    """Todos los asistentes nombrados en `text`: [(asistente, índice de la
    palabra, palabra tal cual)]. Al principio (`first` palabras) y al final
    de la frase vale el umbral normal; en medio, `inner_ratio`."""
    words = tokens(text)
    found = []
    for idx, word in enumerate(words):
        norm = normalize(word)
        if len(norm) < 3:
            continue
        name, r = best_name(norm, names, exclusions)
        edge = idx < first or idx == len(words) - 1
        if name and r >= (ratio if edge else inner_ratio):
            found.append((name, idx, word))
    return found


def canonicalize(text: str, names: dict, exclusions, display: dict, ratio: float = DEFAULT_RATIO,
                 inner_ratio: float = INNER_RATIO) -> str:
    """`text` con cada asistente nombrado escrito como se llama de verdad
    (`display`: {asistente: "Jarvis"}): "Harvis, ¿qué hora es?" → "Jarvis,
    ¿qué hora es?", "Джарвис, …" → "Jarvis, …". Así la conversación (y quien
    decide a quién se le habló) ve el nombre real."""
    mentions = {idx: name for name, idx, _word in find_mentions(text, names, exclusions, ratio, inner_ratio)}
    if not mentions:
        return text
    counter = iter(range(10 ** 6))

    def replace(m):
        idx = next(counter)
        return display.get(mentions[idx], m.group(0)) if idx in mentions else m.group(0)

    return TOKEN_RE.sub(replace, text)


def read_wake_file(path: str = WAKE_WORDS_PATH):
    """Devuelve (cabecera, secciones): `cabecera` son las líneas previas a
    la primera sección (comentarios de ayuda, se conservan al reescribir) y
    `secciones` un dict ordenado {nombre_sección: [palabras...]} tal como
    están escritas (sin comentarios)."""
    header, sections, current = [], {}, None
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return header, sections

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        is_section = line.startswith("[") and line.endswith("]")
        if current is None and not is_section:
            header.append(raw_line.rstrip())
            continue
        if is_section:
            current = line[1:-1].strip().lower()
            sections.setdefault(current, [])
            continue
        if line and line not in sections[current]:
            sections[current].append(line)
    return header, sections


def load_wake_words(path: str = WAKE_WORDS_PATH):
    """Devuelve ({sección: set(variantes normalizadas)}, set(exclusiones
    normalizadas)). Las secciones que no son asistentes se devuelven igual;
    quien llama filtra las que le interesan."""
    _header, sections = read_wake_file(path)
    aliases = {
        name: {normalize(w) for w in words}
        for name, words in sections.items()
        if name != EXCLUDE_SECTION
    }
    exclusions = {normalize(w) for w in sections.get(EXCLUDE_SECTION, [])}
    return aliases, exclusions


def write_wake_file(header: list, sections: dict, path: str = WAKE_WORDS_PATH) -> None:
    """Reescribe wake_words.txt conservando la cabecera de comentarios. Las
    secciones vacías se omiten (salvo "[excluir]", que siempre se deja para
    que se vea dónde agregar palabras)."""
    out = list(header)
    while out and not out[-1].strip():
        out.pop()
    out.append("")
    for name, words in sections.items():
        if not words and name != EXCLUDE_SECTION:
            continue
        out.append(f"[{name}]")
        out.extend(words)
        out.append("")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    os.replace(tmp, path)


_WORD_RE = re.compile(r"^\w+$", re.UNICODE)


def clean_word(word: str) -> str:
    """Normaliza una variante/exclusión escrita a mano; "" si no es UNA
    sola palabra (el reconocimiento compara palabra por palabra)."""
    word = normalize(str(word))
    return word if _WORD_RE.match(word) else ""


def wake_report(name: str, aliases, exclusions, others: dict, ratio: float = DEFAULT_RATIO) -> dict:
    """Revisa qué tan seguro es `name` (+ `aliases`) como palabra de
    activación:
    - `collisions`: palabras comunes (COMMON_WORDS) no excluidas que lo
      activarían por error.
    - `confusions`: nombres/alias de OTROS asistentes (`others`, {nombre:
      set(alias)}) tan parecidos que Whisper podría confundirlos."""
    candidates = {normalize(name)} | {normalize(a) for a in aliases}
    candidates.discard("")
    collisions = {}
    for word in COMMON_WORDS:
        if word in candidates:
            continue
        best = max((match_ratio(word, c, exclusions) for c in candidates), default=0.0)
        if best >= ratio:
            collisions[word] = round(best, 2)

    confusions = []
    for other, other_aliases in others.items():
        best_word, best = None, 0.0
        for other_word in sorted({other} | set(other_aliases)):
            for c in candidates:
                r = similarity(other_word, c)
                if r > best:
                    best_word, best = other_word, r
        if best >= ratio:
            confusions.append({"assistant": other, "word": best_word, "ratio": round(best, 2)})

    return {
        "collisions": [{"word": w, "ratio": r} for w, r in sorted(collisions.items(), key=lambda kv: -kv[1])],
        "confusions": confusions,
    }
