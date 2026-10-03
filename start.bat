@echo off
setlocal
cd /d "%~dp0"

echo.
echo AV Assistant - Windows setup and launch
echo ---------------------------------------

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or later and enable "Add Python to PATH".
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 22 or later, then reopen this window.
  pause
  exit /b 1
)

where pnpm >nul 2>nul
if errorlevel 1 (
  echo pnpm was not found. Run: npm install --global pnpm
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or later is required.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  python -m venv .venv
  if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"
python -c "import fastapi, uvicorn, openai, httpx, dotenv, multipart" >nul 2>nul
if errorlevel 1 (
  echo Installing Python packages...
  python -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :failed
) else (
  echo Python packages are ready.
)

if not exist "node_modules" (
  echo Installing frontend packages...
  call pnpm install
  if errorlevel 1 goto :failed
)

echo Building the browser interface...
set PORT=8765
set BASE_PATH=/
call pnpm --filter @workspace/av-assistant run build
if errorlevel 1 goto :failed

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
  echo Add your provider settings in .env, then start AV Assistant again.
  notepad ".env"
  pause
  exit /b 0
)

echo Opening AV Assistant at http://127.0.0.1:8765
start "" http://127.0.0.1:8765
echo Keep this window open while you use the assistant.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
goto :eof

:failed
echo.
echo Startup stopped because a setup step failed. Read the message above, fix it, and run start.bat again.
pause
exit /b 1