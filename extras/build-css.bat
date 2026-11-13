@echo off
rem Rebuilds app\webui\static\style.css from app\webui\static\src\ with the
rem Tailwind CSS standalone CLI (no Node.js). The first run downloads the CLI
rem to cache\tailwind\ (ignored by git). Extra arguments are passed through,
rem e.g. "build-css.bat --watch" rebuilds on every change.
setlocal
cd /d "%~dp0.."
set "TW_VERSION=v4.3.5"
set "TW=cache\tailwind\tailwindcss-%TW_VERSION%.exe"
if not exist "%TW%" (
  echo Downloading Tailwind CSS %TW_VERSION% standalone CLI...
  if not exist "cache\tailwind" mkdir "cache\tailwind"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/tailwindlabs/tailwindcss/releases/download/%TW_VERSION%/tailwindcss-windows-x64.exe' -OutFile '%TW%'"
  if errorlevel 1 (
    echo Could not download the Tailwind CSS CLI. Check your internet connection.
    if exist "%TW%" del "%TW%"
    exit /b 1
  )
)
echo Building app\webui\static\style.css ...
"%TW%" -i app\webui\static\src\tailwind.css -o app\webui\static\style.css --minify %*
if errorlevel 1 (
  echo CSS build failed.
  exit /b 1
)
echo Done.
