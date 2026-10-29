@echo off
rem One-click start on Windows. The first run creates a virtualenv and installs VIPLAV.
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo Created .env with the free defaults ^(your Claude plan, browser voice^).
)
where claude >nul 2>nul
if errorlevel 1 (
  echo VIPLAV uses your Claude plan through Claude Code, which isn't installed yet.
  echo Install it: open PowerShell and run   irm https://claude.ai/install.ps1 ^| iex
  echo Then run   claude   once to sign in, and start run.bat again.
  pause
  exit /b 1
)
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
  echo Installing VIPLAV ^(the first time takes a few minutes^)...
  .venv\Scripts\python -m pip install -q -e .
)
.venv\Scripts\viplav
pause
