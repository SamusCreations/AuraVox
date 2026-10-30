"""
Idioma evidente de un texto, sin modelos ni dependencias: por el alfabeto
(cirílico, griego, árabe, devanagari, coreano, japonés, vietnamita) y, en
los idiomas con alfabeto latino, por sus palabras funcionales más
frecuentes ("the", "qué", "você"...). Cuando no es claro devuelve None (no
opina) y el que llama decide.

Solo se usa dentro de Whisper (app/voice/stt_whisper.py): al forzar un
idioma para transcribir, si el texto igual salió en otro, eso delata el
idioma real de lo dicho (es una señal más del puntaje, medida con 88
frases). Para todo lo demás (en qué idioma salió la respuesta del modelo,
en qué idioma escribió el usuario) ya no se adivina con listas de palabras:
lo dice el propio modelo (ver assistant_common._review_draft), en
cualquiera de los 31 idiomas.
"""
import re

FUNCTION_WORDS = {
    "en": set("the is are am was were you your what how who when where why can could would will do does did "
              "it this that to of and for with my me please thanks thank hello hi yes i i'm it's what's tell "
              "play some turn up today tomorrow yesterday there they we he she an be have has not".split()),
    "es": set("el la los las es está están son qué cómo quién cuándo dónde por favor gracias hola sí y del al "
              "un una unos unas con para mi tu su dime pon hoy mañana ayer puedes eres soy estoy hay muy pero "
              "también".split()),
    "pt": set("você vocês obrigado obrigada tudo bem não sim os é são da do das dos em um uma com para meu minha "
              "seu sua olá oi hoje amanhã ontem qual pode dizer está estou muito mas também isso".split()),
    "fr": set("le les est sont vous tu je il elle nous qui quoi comment pourquoi merci bonjour oui non et des du "
              "un une avec pour mon ma ton aujourd'hui demain c'est".split()),
    "de": set("der die das ist sind du sie ich wir was wie wer wann warum danke hallo ja nein und mit für mein "
              "dein heute morgen nicht ein eine".split()),
    "it": set("il lo gli è sono tu io lui lei noi che cosa come perché grazie ciao sì e con per mio mia oggi "
              "domani non un una".split()),
}

_WORD_RE = re.compile(r"[\w'’]+")


def _hits(words, vocabularies) -> list:
    return sorted(((sum(w in vocab for w in words), lang) for lang, vocab in vocabularies.items()), reverse=True)


def detect(text: str, short: bool = True):
    """Código del idioma evidente de `text`, o None si no es claro.

    `short=True` (frases dichas al asistente): pide al menos 2 palabras
    funcionales y que sean el 40% del texto. `short=False` (respuestas
    largas): alcanza con 4 y que dupliquen al segundo idioma."""
    words = _WORD_RE.findall(text.lower())
    if not words:
        return None
    hits = _hits(words, FUNCTION_WORDS)
    (best, lang), (second, _) = hits[0], hits[1]
    if best < 2 * second or best < (2 if short else 4):
        return None
    if short and best / len(words) < 0.4:
        return None
    return lang
