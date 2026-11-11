# Desktop shortcut icon fixer.
# Only rewrites IconLocation values containing unexpanded %ENV% tokens.
# Every touched .lnk is backed up to Desktop\ShortcutIconBackup first. Safe to re-run.
#
# Run:  powershell -ExecutionPolicy Bypass -File ".\fix_shortcut_icons.ps1"

$ErrorActionPreference = 'Continue'
$desk   = [Environment]::GetFolderPath('Desktop')
$backup = Join-Path $desk 'ShortcutIconBackup'
if (-not (Test-Path -LiteralPath $backup)) { New-Item -ItemType Directory -Path $backup | Out-Null }

$shell   = New-Object -ComObject WScript.Shell
$changed = 0

Get-ChildItem -LiteralPath $desk -Filter *.lnk | ForEach-Object {
  $f    = $_
  $lnk  = $shell.CreateShortcut($f.FullName)
  $icon = [string]$lnk.IconLocation

  if ($icon -match '%[A-Za-z_][A-Za-z0-9_]*%') {
    Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $backup $f.Name) -Force
    $expanded = [Environment]::ExpandEnvironmentVariables($icon)
    $lnk.IconLocation = $expanded
    $lnk.Save()
    Write-Host "FIXED  $($f.Name)"
    Write-Host "       $icon"
    Write-Host "    -> $expanded"
    $changed++
  }

  $p = (([string]$lnk.IconLocation) -split ',')[0].Trim('"')
  if ($p -and -not (Test-Path -LiteralPath $p)) {
    Write-Host "WARN   $($f.Name): icon target not found: $p"
  }
}

try { & 'ie4uinit.exe' '-show' | Out-Null } catch {}

Write-Host ''
Write-Host "Changed $changed shortcut(s). Backups in: $backup"
Write-Host 'If icons are still blank, restart Explorer or sign out to rebuild IconCache.db.'
