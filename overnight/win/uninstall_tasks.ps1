<#
.SYNOPSIS
  Remove every scheduled task this project installed.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File overnight\win\uninstall_tasks.ps1
#>
[CmdletBinding()]
param([string]$TaskPath = '\Overnight\')

$ErrorActionPreference = 'Stop'
$found = Get-ScheduledTask -TaskPath $TaskPath -ErrorAction SilentlyContinue
if (-not $found) { Write-Host "nothing registered under $TaskPath"; return }

foreach ($t in $found) {
  Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $TaskPath -Confirm:$false
  Write-Host "removed $($t.TaskName)"
}
Write-Host "the strategy will no longer run on its own."
