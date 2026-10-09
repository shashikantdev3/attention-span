# Registers the Attention Span nightly run in Windows Task Scheduler.
# Run once from the repo folder in PowerShell:
#     powershell -ExecutionPolicy Bypass -File tools\schedule_nightly.ps1
#
# What it sets up:
#   - runs tools\nightly.bat every day at 23:45, from 10 October 2026
#   - the schedule ends at 00:00 on Monday 19 October 2026 (the last run is the night of 18 October)
#   - if the laptop was asleep or off at 23:45, it runs as soon as it is back on
#   - it only writes the edition; it never commits or pushes
#
# To change the end date, edit $End below and run this script again.
# To remove it early:  Unregister-ScheduledTask -TaskName "Attention Span nightly" -Confirm:$false

$ErrorActionPreference = "Stop"
$TaskName = "Attention Span nightly"
$Start    = [datetime]"2026-10-10T23:45:00"
$End      = [datetime]"2026-10-19T00:00:00"

$Repo = Split-Path -Parent $PSScriptRoot
$Bat  = Join-Path $PSScriptRoot "nightly.bat"
if (-not (Test-Path $Bat)) { throw "Cannot find $Bat" }

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { throw "python is not on PATH. Install Python 3.12, then run this again." }

$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Bat`"" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Start
$trigger.EndBoundary = $End.ToString("s")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1) -DeleteExpiredTaskAfter (New-TimeSpan -Days 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Writes the Attention Span edition each night. Does not publish." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered '$TaskName'."
Write-Host "  Runs:      every day at 23:45"
Write-Host "  Next run:  $($info.NextRunTime)"
Write-Host "  Ends:      $End"
Write-Host "  Log:       $Repo\state\reports\nightly.log"
