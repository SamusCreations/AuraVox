@echo off
setlocal
rem This folder (extras) is inside the project folder: HERE is the project root.
set "HERE=%~dp0..\"
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
"%PY%" "%HERE%app\core\voice_loop.py"
pause
