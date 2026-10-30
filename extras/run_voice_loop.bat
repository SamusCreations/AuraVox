@echo off
setlocal
rem Esta carpeta (extras) esta dentro de la del proyecto: HERE es la raiz.
set "HERE=%~dp0..\"
set "HF_HOME=%HERE%cache\huggingface"
set "SUPERTONIC_CACHE_DIR=%HERE%cache\supertonic3"
"%HERE%python\python.exe" "%HERE%app\core\voice_loop.py"
pause
