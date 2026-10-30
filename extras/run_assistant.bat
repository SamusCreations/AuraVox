@echo off
setlocal
if "%~1"=="" (
    echo Uso: extrasun_assistant.bat ^<nombre-de-assistants.yaml^>
    echo Ejemplo: extrasun_assistant.bat jarvis
    pause
    exit /b 1
)
rem Esta carpeta (extras) esta dentro de la del proyecto: HERE es la raiz.
set "HERE=%~dp0..\"
set "HF_HOME=%HERE%cache\huggingface"
set "SUPERTONIC_CACHE_DIR=%HERE%cache\supertonic3"
"%HERE%python\python.exe" "%HERE%app\core\assistant_engine.py" %1
pause
