@echo off
rem Pretiahnite PDF so skenom vychystavacich listov na tento subor.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if "%~1"=="" (
  echo Pretiahnite PDF subor na kompletacia.bat
  pause
  exit /b 1
)
python -m kompletacia %* -o "%~dpn1_kompletacia.pdf"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "%~dpn1_kompletacia.pdf"
pause
