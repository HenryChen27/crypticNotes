$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/update-client.ps1" -FunctionsOnly
$testRoot = Join-Path (Split-Path -Parent $PSScriptRoot) ('out/updater-test-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $testRoot 'payload'
$target = Join-Path $testRoot 'installed'
$backup = Join-Path $testRoot 'backup'
[void][IO.Directory]::CreateDirectory((Join-Path $source 'maps'))
[void][IO.Directory]::CreateDirectory((Join-Path $target 'maps'))
[IO.File]::WriteAllText((Join-Path $source 'app.exe'), 'new')
[IO.File]::WriteAllText((Join-Path $source 'maps/floors.json'), 'published maps')
[IO.File]::WriteAllText((Join-Path $target 'app.exe'), 'old')
[IO.File]::WriteAllText((Join-Path $target 'maps/floors.json'), 'custom maps')
[IO.File]::WriteAllText((Join-Path $target 'user.txt'), 'keep')
Install-Payload $source $target $backup
if ([IO.File]::ReadAllText((Join-Path $target 'app.exe')) -ne 'new') { throw 'Replacement failed' }
if ([IO.File]::ReadAllText((Join-Path $backup 'app.exe')) -ne 'old') { throw 'Backup failed' }
if ([IO.File]::ReadAllText((Join-Path $target 'maps/floors.json')) -ne 'custom maps') { throw 'Custom maps overwritten' }
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
Write-Output 'PASS: replacement, backup, map preservation, unknown files, traversal rejection, rollback'
