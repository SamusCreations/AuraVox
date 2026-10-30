"""
Deja listas las DLL de CUDA que traen los paquetes pip `nvidia-*` (carpeta
site-packages/nvidia/<paquete>/bin) para Whisper (ctranslate2) y Supertonic
(onnxruntime-gpu), sin requerir el CUDA Toolkit del sistema, y decide si
Supertonic puede correr en GPU.

Por qué hace falta decidirlo: Supertonic trae la CPU fija
(supertonic.config.DEFAULT_ONNX_PROVIDERS = ["CPUExecutionProvider"]), y si
se le pide CUDA sin tener todas las DLL, onnxruntime vuelve a CPU en
silencio (y llena la consola de errores). Aquí se comprueba antes que las
DLL de la versión de CUDA con la que se compiló onnxruntime se puedan cargar.
"""
import os
import sys

_SITE_PACKAGES = os.path.join(os.path.dirname(os.__file__), "site-packages")
_NVIDIA_PACKAGES = ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime", "cufft", "curand", "nvjitlink")
_dll_dirs_added = False


def add_nvidia_dll_dirs() -> None:
    """Agrega las carpetas bin de los paquetes nvidia-* al buscador de DLL:
    os.add_dll_directory() para la carga "segura" (ctypes, extensiones de
    Python) y también PATH, porque ctranslate2 carga cuBLAS/cuDNN desde su
    propio código C++ con LoadLibrary clásico, que solo mira PATH."""
    global _dll_dirs_added
    if _dll_dirs_added or sys.platform != "win32":
        return
    for pkg in _NVIDIA_PACKAGES:
        bin_dir = os.path.join(_SITE_PACKAGES, "nvidia", pkg, "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    _dll_dirs_added = True


def onnx_providers():
    """(proveedores, motivo) para las sesiones ONNX de Supertonic: CUDA (con
    CPU de respaldo) si onnxruntime-gpu puede cargar de verdad sus DLL; si
    no, solo CPU y el motivo, para mostrarlo en el log."""
    try:
        import onnxruntime as ort
        from onnxruntime.capi import version_info
    except ImportError:
        return ["CPUExecutionProvider"], "onnxruntime is not installed with GPU support"

    # Sin esto, con CUDA se imprime en cada carga un aviso inofensivo
    # ("N Memcpy nodes are added to the graph...") que ensucia la consola.
    ort.set_default_logger_severity(3)

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return ["CPUExecutionProvider"], "this onnxruntime build does not include CUDA support"
    if sys.platform != "win32":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"], "GPU (CUDA)"

    add_nvidia_dll_dirs()
    major = str(getattr(version_info, "cuda_version", "12")).split(".")[0]
    try:
        ort.preload_dlls(msvc=False)
    except Exception:  # noqa: BLE001 — si falla, la comprobación de abajo lo dice
        pass

    import ctypes

    missing = []
    for dll in (f"cudart64_{major}.dll", f"cublasLt64_{major}.dll", f"cublas64_{major}.dll", "cudnn64_9.dll"):
        try:
            ctypes.WinDLL(dll)
        except OSError:
            missing.append(dll)
    if missing:
        return ["CPUExecutionProvider"], (
            f"CPU: onnxruntime-gpu {ort.__version__} requires CUDA {major} and is missing {', '.join(missing)}"
        )
    return ["CUDAExecutionProvider", "CPUExecutionProvider"], f"GPU (CUDA {major})"


def session_device(sessions) -> str:
    """"GPU" si alguna sesión ONNX quedó de verdad en CUDA, si no "CPU"."""
    for s in sessions:
        if "CUDAExecutionProvider" in s.get_providers():
            return "GPU"
    return "CPU"
