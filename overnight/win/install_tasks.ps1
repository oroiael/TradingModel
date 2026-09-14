<#
.SYNOPSIS
  Register the overnight strategy as Windows scheduled tasks, so nothing has to
  be typed during the trading day.

.DESCRIPTION
  Seven tasks under the \Overnight\ folder in Task Scheduler. Times are the
  MACHINE's local clock, and the strategy's deadlines are New York time, so
  this refuses to install unless the machine is on Eastern.

  Every task runs the same wrapper, which logs to overnight\out\<job>.log.

  Missed runs are allowed to start late (-StartWhenAvailable) because every job
  refuses on its own clock: a late `enter` will not send an MOC past 15:50, a
  late `exit` will not send an MOO past 09:29:30, and the watchdog picks up
  whatever that leaves behind. Late is safe here; silent is not.

.PARAMETER Mode
  Live     — enter and exit TRANSMIT. Real orders on whatever account TWS is
             logged in to.
  Rehearse — nothing is ever sent. Same schedule, same logs, no orders.

  There is no default. Which one you meant is not something to infer.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File overnight\win\install_tasks.ps1 -Mode Rehearse
  powershell -ExecutionPolicy Bypass -File overnight\win\install_tasks.ps1 -Mode Live
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Live', 'Rehearse')]
  [string]$Mode,

  [string]$TaskPath = '\Overnight\',

  [switch]$AllowNonEastern
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
$wrapper = Join-Path $here 'run_job.cmd'

if (-not (Test-Path $wrapper)) { throw "missing wrapper: $wrapper" }
if (-not (Test-Path (Join-Path $repo 'overnight\run.py'))) {
  throw "does not look like the TradingModel repo: $repo"
}

# --- the clock ------------------------------------------------------------
# Every time below is New York. A machine on another zone would run `enter` at
# the wrong moment and the 15:50 guard would refuse it, every day, silently.
$tz = [System.TimeZoneInfo]::Local
if ($tz.Id -notmatch 'Eastern' -and -not $AllowNonEastern) {
  throw ("this machine's timezone is '$($tz.Id)', not US Eastern. Every time " +
         "below is New York. Either set the machine to Eastern, or re-run " +
         "with -AllowNonEastern and convert the times yourself first.")
}

# --- the interpreter ------------------------------------------------------
$venv = Join-Path $repo 'env\Scripts\python.exe'
if (Test-Path $venv) {
  Write-Host "python : $venv"
} else {
  Write-Warning "no venv at $venv - the tasks will use whatever 'python' is on PATH."
}

$live = ($Mode -eq 'Live')
$send = if ($live) { '--transmit' } else { '' }

# job, time, flags, why
$jobs = @(
  @{ Name = 'exit';      At = '09:15'; Args = "exit $send";     Why = 'sell at the opening auction' },
  @{ Name = 'watchdog';  At = '09:35'; Args = "watchdog $send"; Why = 'flatten if the exit did not' },
  @{ Name = 'report';    At = '09:45'; Args = 'report';         Why = 'write the P&L row' },
  @{ Name = 'watchdog2'; At = '12:30'; Args = "watchdog $send"; Why = 'midday safety net' },
  @{ Name = 'watchdog3'; At = '15:35'; Args = "watchdog $send"; Why = 'clear anything stuck before entering' },
  @{ Name = 'enter';     At = '15:45'; Args = "enter $send";    Why = 'buy market-on-close' },
  @{ Name = 'confirm';   At = '16:05'; Args = 'confirm';        Why = 'record the fill, unreadable tomorrow' }
)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                                        -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)

Write-Host ""
Write-Host "installing $Mode schedule into $TaskPath" -ForegroundColor Cyan
Write-Host "repo   : $repo"
Write-Host ""

foreach ($j in $jobs) {
  $jobArgs = ($j.Args).Trim()
  $action = New-ScheduledTaskAction -Execute $wrapper -Argument $jobArgs `
                                    -WorkingDirectory $repo
  $trigger = New-ScheduledTaskTrigger -Weekly `
      -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
      -At ([datetime]::ParseExact($j.At, 'HH:mm', $null))

  $name = "Overnight-$($j.Name)"
  Register-ScheduledTask -TaskName $name -TaskPath $TaskPath -Action $action `
      -Trigger $trigger -Principal $principal -Settings $settings `
      -Description "$($j.Why) [$Mode]" -Force | Out-Null

  "{0,-6} {1,-22} {2}" -f $j.At, $name, $j.Why | Write-Host
}

Write-Host ""
if ($live) {
  Write-Host "LIVE. enter and exit will send real orders to whatever account " -ForegroundColor Yellow -NoNewline
  Write-Host "TWS is logged in to." -ForegroundColor Yellow
} else {
  Write-Host "REHEARSE. Nothing will be sent." -ForegroundColor Green
}
Write-Host ""
Write-Host "TWS or Gateway must be running and logged in, this user must be"
Write-Host "logged on, and the machine must be awake. Logs: overnight\out\*.log"
Write-Host ""
Write-Host "check      : Get-ScheduledTask -TaskPath '$TaskPath' | Format-Table TaskName,State"
Write-Host "run one now: Start-ScheduledTask -TaskPath '$TaskPath' -TaskName 'Overnight-report'"
Write-Host "remove all : overnight\win\uninstall_tasks.ps1"
