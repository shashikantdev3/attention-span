# Registers the Attention Span twice-daily run in Windows Task Scheduler.
# Run once from the repo folder in PowerShell:
#     powershell -ExecutionPolicy Bypass -File tools\schedule_twice_daily.ps1
#
# Runs tools\twice_daily.bat every day at 06:30 and 18:30 (laptop time, IST):
#   06:30 IST = 8:00 PM ET / 5:00 PM PT the evening before: the whole US working day is in, India wakes up to it
#   18:30 IST = 8:00 AM ET / 5:00 AM PT: Asia and Europe's day is in, the US wakes up to it
# If the laptop was asleep or off at that time, it wakes the laptop or runs as soon as it is back on.
# It never commits or pushes. Remove it with:
#     Unregister-ScheduledTask -TaskName "Attention Span twice daily" -Confirm:$false

$ErrorActionPreference = "Stop"
$TaskName = "Attention Span twice daily"
$Repo = Split-Path -Parent $PSScriptRoot
$Bat  = Join-Path $PSScriptRoot "twice_daily.bat"
if (-not (Test-Path $Bat)) { throw "Cannot find $Bat" }

$real = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
if (-not $real -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Cannot find Python 3. Install Python 3.12, then run this again."
}

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Bat`"" -WorkingDirectory $Repo
# Catch-up starts: at sign-in and when the laptop is unlocked (5 minutes later). The script only does work at those
# starts if a 06:30 or 18:30 run was missed, for example because the laptop was shut down or hibernating.
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT5M"
$class  = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
$unlock = New-CimInstance -CimClass $class -ClientOnly
$unlock.StateChange = 8          # session unlock
$unlock.UserId = "$env:USERDOMAIN\$env:USERNAME"
$unlock.Delay = "PT5M"
$triggers = @(
  (New-ScheduledTaskTrigger -Daily -At ([datetime]"06:30")),
  (New-ScheduledTaskTrigger -Daily -At ([datetime]"18:30")),
  $logon,
  $unlock
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings `
    -Description "Attention Span: editions, missed stories and Context Window twice a day. Does not publish." -Force | Out-Null

# the old nightly task is replaced by this one
if (Get-ScheduledTask -TaskName "Attention Span nightly" -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName "Attention Span nightly" -Confirm:$false
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered '$TaskName': every day at 06:30 and 18:30, plus a catch-up at sign-in and unlock."
Write-Host "  Next run:  $($info.NextRunTime)"
Write-Host "  Report:    $Repo\state\tmp\publish\PUBLISH.md (opens in Notepad after each run)"
Write-Host "  Run now:   Start-ScheduledTask -TaskName '$TaskName'"
