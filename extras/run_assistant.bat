@echo off
setlocal
if "%~1"=="" (
    echo Usage: extras\run_assistant.bat ^<assistant-name-from-assistants.yaml^>
    echo Example: extras\run_assistant.bat jarvis
    pause
    exit /b 1
)
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
"%PY%" "%HERE%app\core\assistant_engine.py" %1
pause
