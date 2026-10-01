@echo off
REM Halal Stock Signals - local start without Docker (SQLite, development only)
REM Run from Anaconda Prompt or any Command Prompt where "python" and "node" work.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo [X] Python not found. Open "Anaconda Prompt" and run this file again. & pause & exit /b 1)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" || (echo [X] Python 3.11 or newer is required. Your version: & python --version & echo Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^). & pause & exit /b 1)
where node >nul 2>nul || (echo [X] Node.js not found. Install the LTS version from https://nodejs.org then run again. & pause & exit /b 1)
if not exist ".env" (echo [X] .env missing. Copy .env.example to .env and add your keys. & pause & exit /b 1)

echo [1/4] Preparing Python environment (first run takes a few minutes)...
if not exist "backend\.venv\Scripts\python.exe" python -m venv backend\.venv || (echo [X] Could not create venv & pause & exit /b 1)
backend\.venv\Scripts\python.exe -m pip install -q --upgrade pip
python --version
REM --only-binary: use pre-built wheels only, so nothing is compiled (Windows Application Control blocks compilers).
backend\.venv\Scripts\python.exe -m pip install -q --only-binary=:all: -r backend\requirements-local.txt || (echo [X] pip install failed. Send a screenshot of the lines above. & pause & exit /b 1)

echo [2/4] Initialising local database...
pushd backend
.venv\Scripts\python.exe -m app.dev_init || (popd & echo [X] Database init failed & pause & exit /b 1)
popd

echo [3/4] Starting backend on http://localhost:8000 ...
start "HSS backend" cmd /k "cd /d %~dp0backend && echo Backend starting on http://127.0.0.1:8000 - output is saved to backend\backend.log. Keep this window open. && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 > backend.log 2>&1 & type backend.log"

echo [4/4] Starting frontend on http://localhost:5173 ...
pushd frontend
if not exist "node_modules" call npm install --no-audit --no-fund || (popd & echo [X] npm install failed & pause & exit /b 1)
popd
start "HSS frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 8 >nul
start "" http://localhost:5173
echo.
echo Running. Close the two "HSS" windows to stop the app.
endlocal
