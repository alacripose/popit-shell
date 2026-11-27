# Install the desk's launcher as the only way the desk starts.
#
# It writes one shortcut (`Popit Desk`) in the Start Menu and on the Desktop, gives it the
# family icon, and takes the logon watchdog out of the Startup folder: the watchdog restarted
# a healthy desk whenever a status call took longer than its 2.5-second probe. Nothing here
# starts or stops a desk; the shortcut is the launch path.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_desk_launcher.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$launcher = Join-Path $root 'tools\desk_launcher.py'
$png = Join-Path $root 'ui\popit-icon-512.png'
$ico = Join-Path $root 'ui\popit.ico'
$startMenu = [Environment]::GetFolderPath('Programs')
$desktop = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')
$pinned = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'

# The family mark, so the pinned button is not a generic Python icon.
if ((Test-Path $png) -and -not (Test-Path $ico)) {
  Add-Type -AssemblyName System.Drawing
  $source = [System.Drawing.Image]::FromFile($png)
  $bitmap = New-Object System.Drawing.Bitmap 256, 256
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.InterpolationMode = 'HighQualityBicubic'
  $graphics.DrawImage($source, 0, 0, 256, 256)
  $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
  $stream = [System.IO.File]::Create($ico)
  $icon.Save($stream)
  $stream.Close()
  $graphics.Dispose(); $bitmap.Dispose(); $source.Dispose()
}

$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command python.exe -ErrorAction Stop).Source }

function New-DeskShortcut([string]$path) {
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($path)
  $shortcut.TargetPath = $python
  $shortcut.Arguments = '"' + $launcher + '"'
  $shortcut.WorkingDirectory = $root
  $shortcut.Description = 'Popit desk · open or raise the agent window'
  $shortcut.IconLocation = $ico
  $shortcut.WindowStyle = 7
  $shortcut.Save()
}

New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ico) | Out-Null
$startPath = Join-Path $startMenu 'Popit Desk.lnk'
New-DeskShortcut $startPath
$desktopPath = Join-Path $desktop 'Popit Desk.lnk'
if (Test-Path $desktop) { New-DeskShortcut $desktopPath }

# A copy in the pinned folder is what the taskbar reads. Explorer decides whether to show
# it; the Start Menu shortcut is the one the owner can right-click and pin regardless.
$pinnedPath = ''
if (Test-Path $pinned) {
  $pinnedPath = Join-Path $pinned 'Popit Desk.lnk'
  New-DeskShortcut $pinnedPath
}

# The logon watchdog is the probe that replaced the desk. It is kept as a file, not as a
# startup entry: the receipt names where it was moved.
$disabled = Join-Path $root 'runlogs\launcher\disabled'
$moved = @()
foreach ($name in 'Popit Toast.lnk', 'Popit Desk.lnk') {
  $old = Join-Path $startup $name
  if (Test-Path $old) {
    New-Item -ItemType Directory -Force -Path $disabled | Out-Null
    Move-Item -Force $old (Join-Path $disabled $name)
    $moved += $name
  }
}

$receipt = [ordered]@{
  schema = 'popit.desk-launcher-install/1'
  at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  target = $python
  launcher = $launcher
  icon = $ico
  shortcuts = @($startPath, $desktopPath, $pinnedPath) | Where-Object { $_ }
  startup_removed = $moved
  taskbar_folder_writable = [bool]$pinnedPath
}
$out = Join-Path $root 'runlogs\launcher\install.json'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
$receipt | ConvertTo-Json -Depth 5 | Out-File -FilePath $out -Encoding utf8
Get-Content $out
