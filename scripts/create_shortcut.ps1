param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
try {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $launcher = Join-Path $projectRoot 'crypticNotes.cmd'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw 'crypticNotes.cmd is missing. Extract the complete package first.'
    }
    if (-not $OutputDirectory) { $OutputDirectory = $projectRoot }
    # Unicode escapes keep Windows PowerShell 5 compatible with BOM-less UTF-8.
    $linkName = -join ([char[]](0x52A0,0x9875,0x624B,0x8BB0,0x5730,0x56FE,0x63D2,0x4EF6))
    $destination = Join-Path $OutputDirectory ($linkName + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($destination)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = 'crypticNotes map assistant'
    $icon = Join-Path $projectRoot 'docs\images\logo.ico'
    if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = "$icon,0" }
    $shortcut.Save()
    Write-Host "Created: $destination"
    Write-Host 'Move the generated shortcut to your desktop. Keep the application folder in place.'
    exit 0
} catch {
    Write-Error $_
    exit 1
}
