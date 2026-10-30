@echo off
setlocal
rem Esta carpeta (extras) esta dentro de la del proyecto: HERE es la raiz.
set "HERE=%~dp0..\"
"%HERE%python\python.exe" "%HERE%app\scripts\free_ollama_memory.py"
pause
