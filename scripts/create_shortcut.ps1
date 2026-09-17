param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
try {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $launcher = Join-Path $projectRoot 'crypticNotes.cmd'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw 'crypticNotes.cmd is missing. Extract the complete package first.'
    }
    if (-not $OutputDirectory) { $OutputDirectory = $projectRoot }
    $destination = Join-Path $OutputDirectory 'crypticNotes.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($destination)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = 'crypticNotes map assistant'
    $executable = Join-Path $projectRoot 'IdentityVMapAssistant.exe'
    if (Test-Path -LiteralPath $executable) { $shortcut.IconLocation = "$executable,0" }
    $shortcut.Save()
    Write-Host "Created: $destination"
    Write-Host 'Move crypticNotes.lnk to your desktop. Keep the application folder in place.'
    exit 0
} catch {
    Write-Error $_
    exit 1
}
