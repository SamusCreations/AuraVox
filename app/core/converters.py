"""Convertir archivos de un formato a otro (herramienta convert_file).

El asistente la llama cuando se le pide ("pásame esto a PDF", "conviértelo a
png"). Se usa lo que ya hay en la PC, sin instalar nada:

- **Microsoft Office** (Word, Excel, PowerPoint) por automatización COM,
  invisible y con las macros desactivadas: documentos (docx, doc, rtf, odt,
  txt, md, html, pdf → docx), hojas de cálculo (xlsx, xls, csv, ods) y
  presentaciones (pptx, ppt, odp), incluido a PDF. También imagen → PDF.
- **ffmpeg**: imágenes (jpg, png, webp, bmp, gif, tiff, ico), audio (mp3,
  wav, ogg, opus, m4a, flac) y video (mp4, webm, mkv, mov, avi, gif).
- **Python**: lo simple (csv ↔ tsv, documento → txt).

`convert(origen, nombre, destino)` → ruta del archivo nuevo (en una carpeta
temporal) o ConversionError con un mensaje para el modelo.
"""
import csv
import io
import os
import shutil
import subprocess
import tempfile
import time

from app.core import attachments

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TIMEOUT = 180

ALIASES = {
    "jpeg": "jpg", "jpe": "jpg", "tif": "tiff", "word": "docx", "excel": "xlsx", "powerpoint": "pptx",
    "text": "txt", "texto": "txt", "markdown": "md", "htm": "html", "mpeg3": "mp3", "mpeg4": "mp4",
    "oga": "ogg", "aif": "aiff", "ppsx": "pptx",
}

# Sin PDF de entrada: al abrir un PDF, Word muestra un aviso ("convertirá el
# PDF en un documento editable") que no se puede cerrar estando invisible y
# se quedaba colgado.
WORD_IN = {"docx", "doc", "docm", "dotx", "rtf", "odt", "txt", "md", "html", "xml", "wpd"}
WORD_OUT = {"pdf": 17, "docx": 16, "doc": 0, "rtf": 6, "odt": 23, "html": 10}
EXCEL_IN = {"xlsx", "xls", "xlsm", "xlsb", "csv", "ods", "tsv"}
EXCEL_OUT = {"xlsx": 51, "xls": 56, "csv": 62, "ods": 60, "pdf": None, "html": 44}
PPT_IN = {"pptx", "ppt", "pptm", "pps", "odp"}
PPT_OUT = {"pdf": 32, "pptx": 24, "ppt": 1, "odp": 35}
IMAGE = {"jpg", "png", "webp", "bmp", "gif", "tiff", "ico"}
AUDIO = {"mp3", "wav", "ogg", "opus", "m4a", "aac", "flac", "aiff", "wma"}
VIDEO = {"mp4", "webm", "mkv", "mov", "avi", "m4v"}


class ConversionError(Exception):
    pass


def norm_ext(value: str) -> str:
    ext = str(value or "").strip().lower().lstrip(".")
    return ALIASES.get(ext, ext)


def _office(app: str) -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{app}.Application").Close()
        return True
    except OSError:
        return False


def _ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    guess = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "ffmpeg.exe")
    return guess if os.path.isfile(guess) else None


def targets(src_ext: str) -> list:
    """Formatos a los que se puede convertir un archivo de este tipo."""
    src = norm_ext(src_ext)
    out = set()
    if src in WORD_IN and _office("Word"):
        out |= set(WORD_OUT) | {"txt"}
    if src in EXCEL_IN and _office("Excel"):
        out |= set(EXCEL_OUT) | {"tsv"}
    if src in {"csv", "tsv"}:
        out |= {"csv", "tsv"}
    if src in PPT_IN and _office("PowerPoint"):
        out |= set(PPT_OUT)
    if src in attachments.OFFICE_EXTENSIONS or src in {"rtf", "html"}:
        out.add("txt")
    if _ffmpeg():
        if src in IMAGE:
            out |= IMAGE
        if src in AUDIO:
            out |= AUDIO
        if src in VIDEO:
            out |= VIDEO | AUDIO | {"gif"}
    if src in IMAGE and _office("Word"):
        out.add("pdf")
    out.discard(src)
    return sorted(out)


# ── Office por PowerShell (COM) ────────────────────────────────────────
_PS = r"""
param([string]$kind, [string]$src, [string]$dst, [string]$fmt)
$ErrorActionPreference = 'Stop'
function Release($o) { if ($o) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($o) } }
if ($kind -eq 'word' -or $kind -eq 'image') {
  $app = New-Object -ComObject Word.Application
  try {
    $app.Visible = $false; $app.DisplayAlerts = 0; $app.AutomationSecurity = 3
    if ($kind -eq 'image') {
      $doc = $app.Documents.Add()
      $ps = $doc.PageSetup; $ps.LeftMargin = 36; $ps.RightMargin = 36; $ps.TopMargin = 36; $ps.BottomMargin = 36
      $pic = $doc.InlineShapes.AddPicture($src)
      $w = $ps.PageWidth - 72; $h = $ps.PageHeight - 72
      $r = [Math]::Min(1, [Math]::Min($w / $pic.Width, $h / $pic.Height))
      $pic.LockAspectRatio = -1; $pic.Width = $pic.Width * $r
    } else {
      $doc = $app.Documents.Open($src, $false, $true, $false)
    }
    try { $doc.SaveAs2($dst, [int]$fmt) } finally { $doc.Close(0); Release $doc }
  } finally { $app.Quit(); Release $app }
} elseif ($kind -eq 'excel') {
  $app = New-Object -ComObject Excel.Application
  try {
    $app.Visible = $false; $app.DisplayAlerts = $false; $app.AutomationSecurity = 3
    $wb = $app.Workbooks.Open($src, 0, $true)
    try {
      if ($fmt -eq 'pdf') { $wb.ExportAsFixedFormat(0, $dst) } else { $wb.SaveAs($dst, [int]$fmt) }
    } finally { $wb.Close($false); Release $wb }
  } finally { $app.Quit(); Release $app }
} elseif ($kind -eq 'ppt') {
  $app = New-Object -ComObject PowerPoint.Application
  try {
    $app.AutomationSecurity = 3
    $p = $app.Presentations.Open($src, -1, 0, 0)
    try { $p.SaveAs($dst, [int]$fmt) } finally { $p.Close(); Release $p }
  } finally { $app.Quit(); Release $app }
}
if (-not (Test-Path -LiteralPath $dst)) { throw "no se generó el archivo" }
"""


_PROCESS = {"word": "WINWORD", "image": "WINWORD", "excel": "EXCEL", "ppt": "POWERPNT"}


def _kill_hidden_office(kind: str, since: float) -> None:
    """Si Office se colgó (un aviso invisible), cierra la instancia oculta que
    abrimos nosotros: la que empezó después de `since` y no tiene ventana
    (un Word que estés usando no se toca)."""
    name = _PROCESS[kind]
    cmd = (f"$t = [DateTime]::FromFileTime({int((since + 11644473600) * 10_000_000)}); "
           f"Get-Process {name} -ErrorAction SilentlyContinue | "
           "Where-Object { $_.StartTime -ge $t -and -not $_.MainWindowTitle } | Stop-Process -Force")
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=30, creationflags=NO_WINDOW)


def _run_office(kind: str, src: str, dst: str, fmt) -> None:
    script = os.path.join(tempfile.gettempdir(), "auravox_convert.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(_PS)
    since = time.time() - 1
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, kind, src, dst, str(fmt)],
            capture_output=True, text=True, timeout=TIMEOUT, creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        _kill_hidden_office(kind, since)
        raise ConversionError("Office tardó demasiado en convertirlo")
    if proc.returncode != 0 or not os.path.isfile(dst):
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ConversionError(f"Office no pudo convertirlo ({detail[0][:200] if detail else proc.returncode})")


def _run_ffmpeg(src: str, dst: str, dst_ext: str) -> None:
    exe = _ffmpeg()
    if not exe:
        raise ConversionError("no está ffmpeg para convertir imágenes, audio o video")
    args = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", src]
    if dst_ext in AUDIO:
        args += ["-vn"]
    if dst_ext == "ico":
        args += ["-vf", "scale='min(256,iw)':-1"]
    if dst_ext == "gif" and norm_ext(os.path.splitext(src)[1]) in VIDEO:
        args += ["-vf", "fps=12,scale='min(640,iw)':-1:flags=lanczos"]
    if dst_ext == "jpg":
        args += ["-q:v", "2"]
    if dst_ext in IMAGE:
        args += ["-frames:v", "1"] if norm_ext(os.path.splitext(src)[1]) in IMAGE and dst_ext != "gif" else []
    args.append(dst)
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT * 3, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise ConversionError("ffmpeg tardó demasiado")
    if proc.returncode != 0 or not os.path.isfile(dst) or not os.path.getsize(dst):
        raise ConversionError(f"ffmpeg no pudo convertirlo ({(proc.stderr or '').strip()[:200]})")


def convert(src: str, src_name: str, target: str) -> str:
    """Convierte `src` (cuyo nombre original es `src_name`) a `target`."""
    dst_ext = norm_ext(target)
    src_ext = norm_ext(os.path.splitext(src_name)[1])
    possible = targets(src_ext)
    if dst_ext == src_ext:
        raise ConversionError(f"ya está en formato {dst_ext}")
    if dst_ext not in possible:
        raise ConversionError(f"no puedo convertir .{src_ext} a .{dst_ext}"
                              + (f"; sí a: {', '.join(possible)}" if possible else ""))
    work = tempfile.mkdtemp(prefix="auravox_")
    base = os.path.splitext(os.path.basename(src_name))[0] or "archivo"
    # Office y ffmpeg se guían por la extensión: una copia con la correcta (y
    # con el nombre original: Excel lo usa de nombre de la hoja).
    os.makedirs(os.path.join(work, "src"))
    src_copy = os.path.join(work, "src", f"{base}.{ {'md': 'txt'}.get(src_ext, src_ext)}")
    if src_ext in {"txt", "md", "csv", "tsv"}:
        # Texto en UTF-8 con BOM: así Word y Excel no se equivocan de codificación.
        with open(src, "rb") as f:
            text = attachments.decode_text(f.read())
        with open(src_copy, "w", encoding="utf-8-sig", newline="") as f:
            f.write(text)
    else:
        shutil.copyfile(src, src_copy)
    dst = os.path.join(work, f"{base}.{dst_ext}")

    if src_ext in {"csv", "tsv"} and dst_ext in {"csv", "tsv"}:
        with open(src_copy, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter="\t" if src_ext == "tsv" else ","))
        with open(dst, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter="\t" if dst_ext == "tsv" else ",").writerows(rows)
    elif dst_ext == "txt" and src_ext not in WORD_IN - {"txt", "md"}:
        with open(src, "rb") as f:
            result = attachments.extract_text(src_name, f.read())
        with open(dst, "w", encoding="utf-8") as f:
            f.write(result["text"])
    elif dst_ext == "tsv" and src_ext in EXCEL_IN:
        tmp_csv = os.path.join(work, "tmp.csv")
        _run_office("excel", src_copy, tmp_csv, EXCEL_OUT["csv"])
        with open(tmp_csv, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        with open(dst, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter="\t").writerows(rows)
    elif src_ext in IMAGE and dst_ext == "pdf":
        _run_office("image", src_copy, dst, WORD_OUT["pdf"])
    elif src_ext in IMAGE | AUDIO | VIDEO:
        _run_ffmpeg(src_copy, dst, dst_ext)
    elif src_ext in PPT_IN:
        _run_office("ppt", src_copy, dst, PPT_OUT[dst_ext])
    elif src_ext in EXCEL_IN:
        _run_office("excel", src_copy, dst, "pdf" if dst_ext == "pdf" else EXCEL_OUT[dst_ext])
    elif src_ext in WORD_IN and dst_ext == "txt":
        with open(src, "rb") as f:
            result = attachments.extract_text(src_name, f.read())
        with open(dst, "w", encoding="utf-8") as f:
            f.write(result["text"])
    else:
        _run_office("word", src_copy, dst, WORD_OUT[dst_ext])
    if not os.path.isfile(dst) or not os.path.getsize(dst):
        raise ConversionError("la conversión no generó nada")
    return dst
