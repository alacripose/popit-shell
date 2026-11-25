# Kept probe: what the notification area answers about its own icons.
#
# The bar needs the tray's real icons (Steam persistent, Discord's call state), not a
# redrawing of them. This probe asks two questions and writes the answers to stdout:
#   1. is Explorer's bar auto-hidden (StuckRects3 Settings), and where is the window;
#   2. does UI Automation see per-icon elements inside Shell_TrayWnd, with names and rects.
# It never changes a setting and never deletes anything.

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$stuck = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3' -ErrorAction SilentlyContinue
if ($stuck) {
  $bytes = $stuck.Settings
  Write-Output ("stuckrects settings[8]={0} (0x{0:X2}) byte9={1}" -f $bytes[8], $bytes[9])
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ProbeWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string name);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
"@

$tray = [ProbeWin]::FindWindow('Shell_TrayWnd', $null)
$rect = New-Object ProbeWin+RECT
[void][ProbeWin]::GetWindowRect($tray, [ref]$rect)
Write-Output ("tray hwnd={0} visible={1} rect={2},{3} {4}x{5}" -f $tray, [ProbeWin]::IsWindowVisible($tray), $rect.Left, $rect.Top, ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))

[void][ProbeWin]::ShowWindow($tray, 5)
[void][ProbeWin]::SetWindowPos($tray, [IntPtr]::Zero, 0, 1032, 1920, 48, 0x0014)
Start-Sleep -Milliseconds 600
[void][ProbeWin]::GetWindowRect($tray, [ref]$rect)
Write-Output ("after show rect={0},{1} {2}x{3}" -f $rect.Left, $rect.Top, ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))

$root = [System.Windows.Automation.AutomationElement]::FromHandle($tray)
if (-not $root) { Write-Output 'no automation root'; exit 0 }
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
Write-Output ("descendants={0}" -f $all.Count)
$seen = 0
foreach ($node in $all) {
  $seen++
  if ($seen -gt 220) { break }
  $current = $node.Current
  $r = $current.BoundingRectangle
  Write-Output ("{0} | {1} | {2} | {3},{4} {5}x{6}" -f $current.ControlType.ProgrammaticName, $current.Name, $current.AutomationId, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
}
[void][ProbeWin]::ShowWindow($tray, 0)
