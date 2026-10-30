@echo off
setlocal
rem This folder (extras) is inside the project folder: HERE is the project root.
set "HERE=%~dp0..\"
if exist "%HERE%python\python.exe" (
    set "PY=%HERE%python\python.exe"
) else if exist "%HERE%.venv\Scripts\python.exe" (
    set "PY=%HERE%.venv\Scripts\python.exe"
) else if exist "%HERE%venv\Scripts\python.exe" (
    set "PY=%HERE%venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" "%HERE%app\scripts\switch_model.py"
pause
