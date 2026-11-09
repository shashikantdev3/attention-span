@echo off
rem Attention Span twice-daily run, started by Windows Task Scheduler (see tools\schedule_twice_daily.ps1).
rem Writes editions, missed stories and Context Window posts, then shows a notification with the git commands.
rem It never commits or pushes.

setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "state\tmp\publish" mkdir "state\tmp\publish"
echo. >> "state\tmp\publish\run.log"
echo ==== %date% %time% ==== >> "state\tmp\publish\run.log"

set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY set "PY=python"

%PY% tools\twice_daily.py >> "state\tmp\publish\run.log" 2>&1
endlocal
