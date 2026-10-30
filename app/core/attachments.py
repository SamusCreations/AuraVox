"""Archivos adjuntos en el chat escrito: el texto de cada documento, para
dárselo al modelo junto con el mensaje.

Solo biblioteca estándar: los formatos de Office y OpenDocument son ZIP con
XML adentro, así que se leen directo (sin python-docx ni openpyxl). Los PDF
se leen en el navegador con pdf.js (ver app.js), que además puede pasar
las páginas escaneadas como imágenes a los modelos con visión.

`extract_text(nombre, bytes)` → {"text", "format", "chars", "truncated"}.
"""
import html
import io
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

# Cuánto texto de un archivo se le pasa al modelo. Ollama usa 16k tokens de
# contexto: el prompt de sistema y las herramientas ya ocupan ~4k, y lo que
# no entra lo corta del PRINCIPIO (se perdería la personalidad). 24 000
# caracteres son ~6-8k tokens.
MAX_CHARS = 24_000
MAX_BYTES = 40_000_000

# Extensiones que se leen como texto plano (código, datos, notas...).
TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "rst", "log", "csv", "tsv", "json", "jsonl", "ndjson", "yaml", "yml", "toml", "ini", "cfg",
    "conf", "env", "xml", "svg", "srt", "vtt", "tex", "bib", "sql", "py", "pyw", "ipynb", "js", "mjs", "cjs", "ts", "tsx",
    "jsx", "css", "scss", "less", "java", "kt", "kts", "c", "h", "cpp", "hpp", "cc", "cs", "go", "rs", "rb", "php", "pl",
    "lua", "r", "m", "swift", "dart", "scala", "sh", "bash", "zsh", "ps1", "psm1", "bat", "cmd", "vue", "svelte",
    "gradle", "properties", "dockerfile", "makefile", "gitignore", "gd", "asm", "vb", "vbs", "f90", "jl", "hs", "ex",
    "exs", "erl", "clj", "groovy", "tf", "proto", "graphql", "nim", "zig", "v", "sv", "vhd", "lisp", "el", "scm",
}
HTML_EXTENSIONS = {"html", "htm", "xhtml"}
OFFICE_EXTENSIONS = {"docx", "docm", "xlsx", "xlsm", "pptx", "pptm", "odt", "ods", "odp", "epub"}
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | HTML_EXTENSIONS | OFFICE_EXTENSIONS | {"rtf"}


class UnsupportedFile(ValueError):
    pass


def _ext(name: str) -> str:
    base = posixpath.basename(str(name or "").replace("\\", "/")).lower()
    if "." not in base:
        return base  # "Dockerfile", "Makefile"
    return base.rsplit(".", 1)[1]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\u00a0]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Texto plano ────────────────────────────────────────────────────────

def decode_text(data: bytes) -> str:
    """Bytes de un archivo de texto en cualquier codificación → str."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if data.startswith(bom):
            return data.decode(enc, errors="replace").lstrip("\ufeff")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Si no es UTF-8, casi siempre es la codificación de Windows en español,
    # inglés o portugués (cp1252). El detector solo manda cuando reconoce
    # otro alfabeto (cirílico, japonés…): con texto latino confundía cp1252
    # con cp1250 ("eńe" en vez de "eñe").
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(data[:2_000_000]).best()
        latin = {"cp1250", "cp1252", "cp1254", "cp1257", "latin_1", "iso8859_1", "iso8859_2", "iso8859_15",
                 "mac_roman", "mac_latin2", "ascii", "utf_8"}
        if best is not None and best.encoding not in latin:
            return data.decode(best.encoding, errors="replace")
    except Exception:  # noqa: BLE001 — sin el detector, la codificación de Windows
        pass
    return data.decode("cp1252", errors="replace")


def _looks_binary(data: bytes) -> bool:
    """Un ejecutable, una imagen, un .zip…: bytes nulos o muchos caracteres
    de control (un texto, aun en otra codificación, casi no tiene)."""
    sample = data[:8000]
    if not sample or sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False
    if b"\x00" in sample:
        return True
    control = sum(1 for b in sample if b < 32 and b not in (9, 10, 12, 13))
    return control > len(sample) // 50


class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header",
             "footer", "blockquote", "pre", "table", "ul", "ol", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _HTMLText()
    parser.feed(markup)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).split("\n")]
    return "\n".join(lines)


# Grupos de RTF que no son texto del documento (fuentes, colores, estilos,
# metadatos, imágenes) y se saltan enteros.
_RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer", "listtable",
             "listoverridetable", "revtbl", "rsidtbl", "generator", "xmlnstbl", "themedata", "datastore"}
_RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}]+)", re.S)


def _rtf_to_text(raw: str) -> str:
    """RTF a texto: recorre los grupos, salta los que no son contenido y
    traduce los caracteres escapados (\\'f1, \\u241)."""
    out, stack, skip, uc_skip = [], [], False, 0
    for word, num, hexa, sym, brace, text in (m.groups() for m in _RTF_TOKEN.finditer(raw)):
        if brace == "{":
            stack.append(skip)
        elif brace == "}":
            skip = stack.pop() if stack else False
        elif skip:
            continue
        elif sym == "*":
            skip = True  # destino opcional que el lector no conoce
        elif word:
            if word in _RTF_SKIP:
                skip = True
            elif word in ("par", "line", "sect", "page", "row"):
                out.append("\n")
            elif word in ("tab", "cell"):
                out.append("\t")
            elif word == "u" and num:
                out.append(chr(int(num) % 65536))
                uc_skip = 1  # el carácter alternativo que sigue
        elif hexa:
            if uc_skip:
                uc_skip = 0
            else:
                out.append(bytes([int(hexa, 16)]).decode("cp1252", "replace"))
        elif sym:
            out.append(sym if sym in "\\{}" else "")
        elif text:
            text = text.replace("\r", "").replace("\n", "")
            if uc_skip and text:
                text, uc_skip = text[1:], 0
            out.append(text)
    return "".join(out)


# ── Office (OOXML) ─────────────────────────────────────────────────────

def _docx(z: zipfile.ZipFile) -> str:
    parts = ["word/document.xml"] + sorted(n for n in z.namelist() if re.match(r"word/(footnotes|endnotes)\.xml$", n))
    out = []
    for part in parts:
        if part not in z.namelist():
            continue
        root = ET.fromstring(z.read(part))
        for p in root.iter():
            if _local(p.tag) != "p":
                continue
            buf = []
            for el in p.iter():
                name = _local(el.tag)
                if name == "t" and el.text:
                    buf.append(el.text)
                elif name == "tab":
                    buf.append("\t")
                elif name in ("br", "cr"):
                    buf.append("\n")
            out.append("".join(buf))
    return "\n".join(out)


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    n = 0
    for ch in letters.group(0) if letters else "":
        n = n * 26 + ord(ch) - 64
    return max(n - 1, 0)


def _xlsx(z: zipfile.ZipFile) -> str:
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
    # Nombre de cada hoja según el libro (en orden), con su archivo.
    sheets = []
    try:
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        for s in ET.fromstring(z.read("xl/workbook.xml")).iter():
            if _local(s.tag) == "sheet":
                rid = next((v for k, v in s.attrib.items() if _local(k) == "id"), None)
                target = rels.get(rid, "")
                path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
                sheets.append((s.get("name") or path, path))
    except (KeyError, ET.ParseError):
        pass
    if not sheets:
        sheets = [(n, n) for n in sorted(names) if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    out = []
    for title, path in sheets:
        if path not in names:
            continue
        rows = []
        for row in ET.fromstring(z.read(path)).iter():
            if _local(row.tag) != "row":
                continue
            cells = {}
            for c in row:
                if _local(c.tag) != "c":
                    continue
                kind, value = c.get("t"), None
                for child in c:
                    if _local(child.tag) == "v":
                        value = child.text
                    elif _local(child.tag) == "is":
                        value = "".join(t.text or "" for t in child.iter() if _local(t.tag) == "t")
                if kind == "s" and value is not None:
                    value = shared[int(value)] if value.isdigit() and int(value) < len(shared) else value
                elif kind == "b" and value is not None:
                    value = "TRUE" if value == "1" else "FALSE"
                if value not in (None, ""):
                    cells[_col_index(c.get("r"))] = value.replace("\t", " ").replace("\n", " ")
            if cells:
                rows.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)))
        if rows:
            out.append(f"## {title}\n" + "\n".join(rows))
    return "\n\n".join(out)


def _pptx(z: zipfile.ZipFile) -> str:
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    out = []
    for name in slides:
        i = int(re.search(r"(\d+)\.xml$", name).group(1))
        paras = []
        for p in ET.fromstring(z.read(name)).iter():
            if _local(p.tag) == "p":
                line = "".join(t.text or "" for t in p.iter() if _local(t.tag) == "t").strip()
                if line:
                    paras.append(line)
        notes = f"ppt/notesSlides/notesSlide{i}.xml"
        if notes in z.namelist():
            note_text = " ".join(t.text or "" for t in ET.fromstring(z.read(notes)).iter() if _local(t.tag) == "t").strip()
            if note_text:
                paras.append(f"(Notes: {note_text})")
        out.append(f"## Slide {i}\n" + "\n".join(paras))
    return "\n\n".join(out)


# ── OpenDocument (LibreOffice) ─────────────────────────────────────────

def _odf(z: zipfile.ZipFile) -> str:
    root = ET.fromstring(z.read("content.xml"))
    out = []

    def text_of(el) -> str:
        buf = [el.text or ""]
        for child in el:
            name = _local(child.tag)
            if name == "s":
                buf.append(" " * int(next((v for k, v in child.attrib.items() if _local(k) == "c"), "1")))
            elif name == "tab":
                buf.append("\t")
            elif name == "line-break":
                buf.append("\n")
            else:
                buf.append(text_of(child))
            buf.append(child.tail or "")
        return "".join(buf)

    def walk(el):
        name = _local(el.tag)
        if name in ("p", "h"):
            out.append(text_of(el))
            return
        if name == "table-row":
            cells = []
            for cell in el:
                if _local(cell.tag) not in ("table-cell", "covered-table-cell"):
                    continue
                value = " ".join(text_of(p) for p in cell if _local(p.tag) in ("p", "h"))
                repeat = int(next((v for k, v in cell.attrib.items() if _local(k) == "number-columns-repeated"), "1"))
                cells += [value] * min(repeat, 50)
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append("\t".join(cells))
            return
        if name == "table":
            title = next((v for k, v in el.attrib.items() if _local(k) == "name"), "")
            if title:
                out.append(f"\n## {title}")
        if name == "page":
            out.append("\n## " + (next((v for k, v in el.attrib.items() if _local(k) == "name"), "") or "Slide"))
        for child in el:
            walk(child)

    walk(root)
    return "\n".join(out)


def _epub(z: zipfile.ZipFile) -> str:
    names = z.namelist()
    order = []
    try:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf = next(el.get("full-path") for el in container.iter() if _local(el.tag) == "rootfile")
        root = ET.fromstring(z.read(opf))
        base = posixpath.dirname(opf)
        items = {el.get("id"): el.get("href") for el in root.iter() if _local(el.tag) == "item"}
        for ref in root.iter():
            if _local(ref.tag) == "itemref" and items.get(ref.get("idref")):
                order.append(posixpath.normpath(posixpath.join(base, items[ref.get("idref")])))
    except (KeyError, StopIteration, ET.ParseError):
        pass
    order = [n for n in order if n in names] or sorted(n for n in names if n.endswith((".xhtml", ".html", ".htm")))
    return "\n\n".join(html_to_text(decode_text(z.read(n))) for n in order)


# ── Entrada ────────────────────────────────────────────────────────────

def extract_text(name: str, data: bytes, limit: int = MAX_CHARS) -> dict:
    """Texto de un documento. `limit`: cuánto texto se devuelve como mucho
    (los adjuntos del chat, MAX_CHARS; los documentos de conocimiento de un
    asistente, mucho más: se parten en trozos)."""
    ext = _ext(name)
    if ext in OFFICE_EXTENSIONS:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if ext in ("docx", "docm"):
                    text, fmt = _docx(z), "Word"
                elif ext in ("xlsx", "xlsm"):
                    text, fmt = _xlsx(z), "Excel"
                elif ext in ("pptx", "pptm"):
                    text, fmt = _pptx(z), "PowerPoint"
                elif ext == "epub":
                    text, fmt = _epub(z), "EPUB"
                else:
                    text, fmt = _odf(z), "OpenDocument"
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
            raise UnsupportedFile(f"no pude leer el archivo ({e})")
    elif ext == "rtf":
        text, fmt = _rtf_to_text(decode_text(data)), "RTF"
    elif ext in HTML_EXTENSIONS:
        text, fmt = html_to_text(decode_text(data)), "HTML"
    elif ext in TEXT_EXTENSIONS or not _looks_binary(data):
        text, fmt = decode_text(data), (ext.upper() if ext in TEXT_EXTENSIONS and len(ext) <= 5 else "TXT")
    else:
        raise UnsupportedFile("no es un documento de texto")
    text = _clean(html.unescape(text) if fmt == "RTF" else text)
    total = len(text)
    return {"text": text[:limit], "format": fmt, "chars": total, "truncated": total > limit}
