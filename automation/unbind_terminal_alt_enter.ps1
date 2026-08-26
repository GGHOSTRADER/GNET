[CmdletBinding()]
param()

$settingsPath = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'
if (-not (Test-Path -LiteralPath $settingsPath)) {
    throw "Windows Terminal settings were not found at: $settingsPath"
}

$content = [System.IO.File]::ReadAllText($settingsPath)
if ($content -match '"keys"\s*:\s*"alt\+enter"') {
    Write-Host 'Alt+Enter already has an explicit Windows Terminal binding; no change made.'
    exit 0
}

$newline = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
$oldLines = @(
    '        {',
    '            "id": "Terminal.DuplicatePaneAuto",',
    '            "keys": "alt+shift+d"',
    '        }'
)
$newLines = @(
    '        {',
    '            "id": "Terminal.DuplicatePaneAuto",',
    '            "keys": "alt+shift+d"',
    '        },',
    '        {',
    '            "id": null,',
    '            "keys": "alt+enter"',
    '        }'
)
$oldBlock = $oldLines -join $newline
$newBlock = $newLines -join $newline

if (-not $content.Contains($oldBlock)) {
    throw 'Expected keybindings anchor was not found; Windows Terminal settings were left untouched.'
}

$backupPath = "$settingsPath.gnet-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -LiteralPath $settingsPath -Destination $backupPath -Force

$updated = $content.Replace($oldBlock, $newBlock)
if ($updated -eq $content -or $updated -notmatch '"id"\s*:\s*null\s*,\s*"keys"\s*:\s*"alt\+enter"') {
    throw 'Alt+Enter unbind could not be verified; settings were not written.'
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($settingsPath, $updated, $utf8NoBom)

Write-Host "Alt+Enter is now passed through by Windows Terminal."
Write-Host "Backup: $backupPath"
