$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/update-client.ps1" -FunctionsOnly
function Merge-MapLibrary([string]$Payload, [string]$OldMaps, [string]$NewMaps) {
    & "$PSScriptRoot/../.venv/Scripts/python.exe" -c "from pathlib import Path; import sys; from mapmatching.src.map_update import merge; merge(Path(sys.argv[1]),Path(sys.argv[2]))" $OldMaps $NewMaps
    if ($LASTEXITCODE -ne 0) { throw 'Merge failed' }
}
$testRoot = Join-Path (Split-Path -Parent $PSScriptRoot) ('out/updater-test-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $testRoot 'payload'
$target = Join-Path $testRoot 'installed'
$backup = Join-Path $testRoot 'backup'
[void][IO.Directory]::CreateDirectory((Join-Path $source 'maps'))
[void][IO.Directory]::CreateDirectory((Join-Path $target 'maps'))
[IO.File]::WriteAllText((Join-Path $source 'app.exe'), 'new')
[IO.File]::WriteAllText((Join-Path $source 'maps/floors.json'), '{"references": []}')
[IO.File]::WriteAllText((Join-Path $source 'maps/new-map.png'), 'new map')
[IO.File]::WriteAllText((Join-Path $target 'app.exe'), 'old')
[IO.File]::WriteAllText((Join-Path $target 'maps/floors.json'), '{"references": []}')
[IO.File]::WriteAllText((Join-Path $target 'maps/local-only.png'), 'local map')
[IO.File]::WriteAllText((Join-Path $target 'user.txt'), 'keep')
Install-Payload $source $target $backup
if ([IO.File]::ReadAllText((Join-Path $target 'app.exe')) -ne 'new') { throw 'Replacement failed' }
if ([IO.File]::ReadAllText((Join-Path $backup 'app.exe')) -ne 'old') { throw 'Backup failed' }
if (((Get-Content (Join-Path $target 'maps/floors.json') -Raw | ConvertFrom-Json).references.Count -ne 0)) { throw 'Published maps were not installed' }
if (-not (Test-Path -LiteralPath (Join-Path $target 'maps/new-map.png'))) { throw 'New published map missing' }
if (-not (Test-Path -LiteralPath (Join-Path $target 'maps/local-only.png'))) { throw 'User map lost' }
if ([IO.File]::ReadAllText((Join-Path $target 'user.txt')) -ne 'keep') { throw 'Untracked file lost' }
$blocked = $false
try { Resolve-Child $target '../escape.txt' } catch { $blocked = $true }
if (-not $blocked) { throw 'Traversal accepted' }
# A late failure must roll back earlier successful replacements.
[IO.File]::WriteAllText((Join-Path $source 'app.exe'), 'newer')
[IO.File]::WriteAllText((Join-Path $source 'zzz.exe'), 'new')
[void][IO.Directory]::CreateDirectory((Join-Path $target 'zzz.exe'))
$failed = $false
try { Install-Payload $source $target (Join-Path $testRoot 'rollback') } catch { $failed = $true }
if (-not $failed) { throw 'Expected replacement failure' }
if ([IO.File]::ReadAllText((Join-Path $target 'app.exe')) -ne 'new') { throw 'Rollback failed' }
if (((Get-Content (Join-Path $target 'maps/floors.json') -Raw | ConvertFrom-Json).references.Count -ne 0)) { throw 'Map rollback failed' }
Write-Output 'PASS: replacement, backup, authoritative maps, unknown files, traversal rejection, rollback'
