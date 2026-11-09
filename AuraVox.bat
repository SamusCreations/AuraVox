@echo off
title AuraVox
setlocal
set "HERE=%~dp0"
set "HF_HOME=%HERE%cache\huggingface"
set "SUPERTONIC_CACHE_DIR=%HERE%cache\supertonic3"

if exist "%HERE%python\python.exe" (
    set "PY=%HERE%python\python.exe"
) else if exist "%HERE%.venv\Scripts\python.exe" (
    set "PY=%HERE%.venv\Scripts\python.exe"
) else if exist "%HERE%venv\Scripts\python.exe" (
    set "PY=%HERE%venv\Scripts\python.exe"
) else (
    set "PY=python"
)

rem Start Ollama and, if its plugin is enabled, ComfyUI (see app\scripts\start_services.py).
"%PY%" "%HERE%app\scripts\start_services.py"

"%PY%" "%HERE%app\webui\config_ui.py" %*
pause
