@echo off
REM Collects the facts needed to choose how to run the app. Writes diagnostics.txt next to this file.
cd /d "%~dp0"
set OUT=diagnostics.txt
echo Halal Stock Signals diagnostics > %OUT%
echo Date: %DATE% %TIME% >> %OUT%
echo. >> %OUT%
echo [Windows] >> %OUT%
ver >> %OUT%
echo. >> %OUT%
echo [Smart App Control: 0=Off 1=On 2=Evaluation] >> %OUT%
reg query "HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy" /v VerifiedAndReputablePolicyState >> %OUT% 2>&1
echo. >> %OUT%
echo [Python] >> %OUT%
where python >> %OUT% 2>&1
python --version >> %OUT% 2>&1
echo. >> %OUT%
echo [Anaconda base packages] >> %OUT%
python -c "import pydantic_core, sqlalchemy, fastapi; print('base OK', pydantic_core.__version__, sqlalchemy.__version__, fastapi.__version__)" >> %OUT% 2>&1
echo. >> %OUT%
echo [Project venv packages] >> %OUT%
if exist "backend\.venv\Scripts\python.exe" (backend\.venv\Scripts\python.exe -c "import pydantic_core; print('venv OK')" >> %OUT% 2>&1) else (echo no venv >> %OUT%)
echo. >> %OUT%
echo [Conda] >> %OUT%
where conda >> %OUT% 2>&1
echo. >> %OUT%
echo [Node] >> %OUT%
where node >> %OUT% 2>&1
node -v >> %OUT% 2>&1
echo. >> %OUT%
echo [Docker] >> %OUT%
where docker >> %OUT% 2>&1
echo. >> %OUT%
echo [WSL] >> %OUT%
wsl --status >> %OUT% 2>&1
echo Done. >> %OUT%
echo Diagnostics saved to %CD%\%OUT%. You can close this window.
pause
