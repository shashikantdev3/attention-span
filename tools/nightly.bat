@echo off
rem Attention Span nightly run, started by Windows Task Scheduler (see tools\schedule_nightly.ps1).
rem It writes the edition and a report. It never commits or pushes: review, then publish yourself.

setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if not exist "state\reports" mkdir "state\reports"
echo. >> "state\reports\nightly.log"
echo ==== %date% %time% ==== >> "state\reports\nightly.log"

python run_daily.py >> "state\reports\nightly.log" 2>&1
if errorlevel 1 (
  echo Run did not finish. If it stopped part way, run: python run_daily.py --resume >> "state\reports\nightly.log"
  exit /b 1
)
echo Finished. Review state\reports, then publish with git. >> "state\reports\nightly.log"
endlocal
