# Restart the Popit desk as one process.
#
# Run detached, never from a shell that belongs to a supervisor's own tree: killing a
# supervisor takes its descendants with it, so a command that is itself a descendant dies
# mid-cleanup (exit 255). Supervisors are found by command line on every process (a WMI
# class filter with `-Filter "Name='python.exe' or ..."` matched nothing here, which is how
# five supervisors survived a cleanup and kept respawning desks), then each tree is ended
# with taskkill, and exactly one locked supervisor is started.

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Get-Supervisors {
  Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*supervise_toast*' } |
    Select-Object -ExpandProperty ProcessId
}

function Get-DeskPids {
  $pids = @()
  foreach ($port in 5207, 5209, 5210, 5211) {
    foreach ($line in (netstat -ano | Select-String ":$port " | Select-String 'LISTEN')) {
      $parts = ($line -split '\s+') | Where-Object { $_ }
      if ($parts.Count -ge 4) { $pids += [int]$parts[-1] }
    }
  }
  $pids | Sort-Object -Unique
}

$supervisors = @(Get-Supervisors)
foreach ($id in $supervisors) { taskkill /F /T /PID $id | Out-Null }
Start-Sleep -Seconds 3

$desks = @(Get-DeskPids)
foreach ($id in $desks) { taskkill /F /T /PID $id | Out-Null }
Start-Sleep -Seconds 4

# A leftover lock from a dead supervisor must not block the new one.
Remove-Item (Join-Path $root 'runlogs\toast\supervisor.lock') -Force

$log = Join-Path $root 'runlogs\toast\supervisor.log'
$proc = Start-Process -FilePath 'python' -ArgumentList 'tools/supervise_toast.py' `
  -WorkingDirectory $root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput $log -RedirectStandardError $log
Start-Sleep -Seconds 50

$left = @(Get-Supervisors)
$desksNow = @(Get-DeskPids)
$answer = 'no'
try {
  $reply = Invoke-WebRequest -Uri 'http://127.0.0.1:5207/api/toast' -TimeoutSec 8 -UseBasicParsing
  if ($reply.StatusCode -eq 200) { $answer = 'yes' }
} catch { $answer = 'no' }

[pscustomobject]@{
  supervisor = $proc.Id
  stopped_supervisors = ($supervisors -join ',')
  stopped_desks = ($desks -join ',')
  supervisors_now = ($left -join ',')
  desks_now = ($desksNow -join ',')
  api_answers = $answer
} | ConvertTo-Json -Compress | Out-File -FilePath (Join-Path $root 'runlogs\toast\restart.json') -Encoding utf8
Get-Content (Join-Path $root 'runlogs\toast\restart.json')
