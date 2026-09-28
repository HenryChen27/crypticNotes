param([string]$InstallRoot = '', [switch]$Detached, [switch]$FunctionsOnly)
$ErrorActionPreference = 'Stop'

function Resolve-Child([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw '更新路径必须为相对路径' }
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath((Join-Path $rootPath $Relative))
    if (-not $target.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) { throw '更新路径越界' }
    # Never follow junctions/symlinks into another installation or user directory.
    $node = $target
    while ($node -and $node.Length -ge $rootPath.TrimEnd('\').Length) {
        if ((Test-Path -LiteralPath $node) -and ((Get-Item -LiteralPath $node -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '更新目录中存在链接，请解压到普通文件夹后更新'
        }
        $node = Split-Path -Parent $node
    }
    return $target
}

function Install-Payload([string]$Payload, [string]$Destination, [string]$Backup) {
    # Preserve the whole local map library (including enrollment, deletions and caches).
    # Settings/records already live in LOCALAPPDATA; never mirror/delete the user's folder.
    $changed = [Collections.Generic.List[object]]::new()
    try {
        foreach ($file in Get-ChildItem -LiteralPath $Payload -File -Recurse) {
            $relative = $file.FullName.Substring($Payload.TrimEnd('\').Length + 1)
            if ($relative -match '^(maps|out|records|\.git)(\\|$)' -or $relative -eq '.windows-update.json') { continue }
            $target = Resolve-Child $Destination $relative
            $saved = Resolve-Child $Backup $relative
            if (Test-Path -LiteralPath $target -PathType Container) { throw '目标文件被同名目录占用' }
            $existed = Test-Path -LiteralPath $target -PathType Leaf
            if ($existed) {
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $saved))
                Copy-Item -LiteralPath $target -Destination $saved -Force
            }
            $changed.Add(@{Target=$target; Saved=$saved; Existed=$existed})
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
            Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        }
    } catch {
        $failure = $_
        $rollbackErrors = @()
        for ($i=$changed.Count-1; $i -ge 0; $i--) {
            $entry = $changed[$i]
            try {
                if ($entry.Existed) { Copy-Item -LiteralPath $entry.Saved -Destination $entry.Target -Force }
                elseif (Test-Path -LiteralPath $entry.Target -PathType Leaf) { Remove-Item -LiteralPath $entry.Target -Force }
            } catch { $rollbackErrors += $_.Exception.Message }
        }
        if ($rollbackErrors.Count) { throw "更新失败且部分回退失败；备份：$Backup。请勿启动程序。$($rollbackErrors -join '; ')" }
        throw "替换失败，已恢复原文件。$($failure.Exception.Message)"
    }
}

if ($FunctionsOnly) { return }
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
# Run a copy outside the installation so replacing the updater itself is safe.
if (-not $Detached) {
    $tempScript = Join-Path ([IO.Path]::GetTempPath()) ('crypticnotes-update-' + [Guid]::NewGuid().ToString('N') + '.ps1')
    Copy-Item -LiteralPath $PSCommandPath -Destination $tempScript
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',('"'+$tempScript+'"'),'-Detached','-InstallRoot',('"'+$InstallRoot+'"'))
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$mutexKey = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($InstallRoot.ToLowerInvariant())).Replace('\','_').Replace('/','_')
$mutex = [Threading.Mutex]::new($false, ('Local\CrypticNotesUpdate-' + $mutexKey))
$locked = $false
try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
if (-not $locked) { exit }
$form = [Windows.Forms.Form]::new()
$form.Text = '加页手记 · 更新'
$form.ClientSize = [Drawing.Size]::new(440,160)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.BackColor = [Drawing.Color]::FromArgb(37,55,69)
$form.ForeColor = [Drawing.Color]::FromArgb(224,235,242)
$form.Font = [Drawing.Font]::new('Microsoft YaHei UI',10)
$label = [Windows.Forms.Label]::new()
$label.SetBounds(22,18,396,62)
$label.Text = '正在检查更新…'
$bar = [Windows.Forms.ProgressBar]::new()
$bar.SetBounds(22,88,396,12)
$bar.Style = 'Marquee'
$button = [Windows.Forms.Button]::new()
$button.SetBounds(308,116,110,30)
$button.Text = '取消'
$button.FlatStyle = 'Flat'
$button.Add_Click({ $form.Close() })
$form.Controls.AddRange(@($label,$bar,$button))
$form.Show()
$work = Join-Path ([IO.Path]::GetTempPath()) ('crypticnotes-package-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($work)
$client = [Net.WebClient]::new()
$client.Headers['User-Agent'] = 'CrypticNotes-Windows-Updater'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$completed = $false
function Download([string]$Url, [string]$Path, [long]$Size = 0) {
    if (-not $Url.StartsWith('https://github.com/HenryChen27/crypticNotes/releases/download/')) { throw '更新地址不是项目官方发布地址' }
    $task = $client.DownloadFileTaskAsync([Uri]$Url, $Path)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not $task.IsCompleted) {
        [Windows.Forms.Application]::DoEvents()
        if ($form.IsDisposed) { $client.CancelAsync(); throw '已取消更新' }
        if ($timer.Elapsed.TotalMinutes -gt 30) { $client.CancelAsync(); throw '下载超时，请稍后重试' }
        if ($Size -gt 0 -and (Test-Path -LiteralPath $Path)) {
            $bytes = (Get-Item -LiteralPath $Path).Length
            $bar.Style = 'Continuous'
            $bar.Value = [Math]::Min(100, [int](100*$bytes/$Size))
            $label.Text = ('正在下载 {0:N1} / {1:N1} MB' -f ($bytes/1MB),($Size/1MB))
        }
        Start-Sleep -Milliseconds 80
    }
    $task.GetAwaiter().GetResult()
}
try {
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'IdentityVMapAssistant.exe'))) { throw '请从完整解压的 Windows 程序目录运行更新' }
    # Public API: no Git, token or GitHub account required.
    $task = $client.DownloadStringTaskAsync('https://api.github.com/repos/HenryChen27/crypticNotes/releases/latest')
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not $task.IsCompleted) {
        [Windows.Forms.Application]::DoEvents()
        if ($form.IsDisposed -or $timer.Elapsed.TotalSeconds -gt 40) { $client.CancelAsync(); throw '检查已取消或超时' }
        Start-Sleep -Milliseconds 80
    }
    $release = $task.GetAwaiter().GetResult() | ConvertFrom-Json
    $asset = @($release.assets | Where-Object name -eq 'IdentityVMapAssistant-Windows-x64.zip')
    $checksum = @($release.assets | Where-Object name -eq 'SHA256SUMS.txt')
    if ($asset.Count -ne 1 -or $checksum.Count -ne 1) { throw '发布包正在维护，请稍后重试' }
    $hashFile = Join-Path $work 'SHA256SUMS.txt'
    Download $checksum[0].browser_download_url $hashFile
    $hashText = Get-Content -LiteralPath $hashFile -Raw -Encoding UTF8
    if ($hashText -notmatch '(?im)^([a-f0-9]{64})\s+\*?IdentityVMapAssistant-Windows-x64\.zip\s*$') { throw '发布校验信息不完整' }
    $expected = $Matches[1].ToLowerInvariant()
    $stampPath = Join-Path $InstallRoot '.windows-update.json'
    $installed = if (Test-Path -LiteralPath $stampPath) { Get-Content -LiteralPath $stampPath -Raw | ConvertFrom-Json } else { $null }
    $manifest = @($release.assets | Where-Object name -eq 'windows-update.json')
    $sameBuild = $false
    if ($manifest.Count -eq 1) {
        $manifestFile = Join-Path $work 'windows-update.json'
        Download $manifest[0].browser_download_url $manifestFile
        $remote = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
        $buildFile = Join-Path $InstallRoot 'windows-build.json'
        if ($remote.sha256 -ne $expected) { throw '发布文件正在更新，请稍后重试' }
        if (Test-Path -LiteralPath $buildFile) {
            $local = Get-Content -LiteralPath $buildFile -Raw | ConvertFrom-Json
            $sameBuild = $local.build -eq $remote.build
        }
    }
    if ($sameBuild -or ($installed -and $installed.sha256 -eq $expected)) {
        $label.Text = '已经是最新版本'
    } else {
        $zip = Join-Path $work 'update.zip'
        Download $asset[0].browser_download_url $zip $asset[0].size
        $label.Text = '正在校验并解压…'
        $bar.Style = 'Marquee'
        [Windows.Forms.Application]::DoEvents()
        if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw '下载校验失败，原程序未修改，请重新更新' }
        if ($asset[0].digest -and $asset[0].digest -ne ('sha256:'+$expected)) { throw '发布文件校验不一致，请稍后重试' }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $extracted = Join-Path $work 'extracted'
        # Validate every entry before extraction, including traversal / absolute paths.
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try { foreach ($entry in $archive.Entries) { [void](Resolve-Child $extracted $entry.FullName) } } finally { $archive.Dispose() }
        [IO.Compression.ZipFile]::ExtractToDirectory($zip,$extracted)
        $payload = Join-Path $extracted 'IdentityVMapAssistant'
        if (-not (Test-Path -LiteralPath (Join-Path $payload 'IdentityVMapAssistant.exe'))) { throw '安装包结构不正确' }
        if ($form.IsDisposed) { throw '已取消更新' }
        $label.Text = '正在退出插件并安装，请勿关闭电脑…'
        $button.Enabled = $false
        $form.ControlBox = $false
        [Windows.Forms.Application]::DoEvents()
        $appPath = [IO.Path]::GetFullPath((Join-Path $InstallRoot 'IdentityVMapAssistant.exe'))
        $running = @(Get-Process -Name IdentityVMapAssistant -ErrorAction SilentlyContinue | Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $appPath })
        foreach ($process in $running) { [void]$process.CloseMainWindow() }
        if ($running.Count) { Start-Sleep -Milliseconds 1200 }
        foreach ($process in @(Get-Process -Name IdentityVMapAssistant -ErrorAction SilentlyContinue | Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $appPath })) {
            Stop-Process -Id $process.Id -Force
            Wait-Process -Id $process.Id -Timeout 8 -ErrorAction SilentlyContinue
        }
        Install-Payload $payload $InstallRoot (Join-Path $work 'backup')
        @{sha256=$expected} | ConvertTo-Json | Set-Content -LiteralPath $stampPath -Encoding UTF8
        $label.Text = '更新完成，设置和本地地图库已保留。'
        Start-Process -FilePath $appPath -WorkingDirectory $InstallRoot -WindowStyle Hidden
    }
    $bar.Style = 'Continuous'
    $bar.Value = 100
    $completed = $true
} catch {
    if (-not $form.IsDisposed) { $label.Text = "更新未完成：$($_.Exception.Message)" }
} finally {
    $client.Dispose()
    if (-not $form.IsDisposed) {
        $button.Text = '关闭'
        $button.Enabled = $true
        $form.ControlBox = $true
        while (-not $form.IsDisposed) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 100 }
    }
    # Only remove this run's generated temporary directory after success.
    # Failed installations retain the backup for manual recovery.
    if ($completed) {
        $resolvedWork = [IO.Path]::GetFullPath($work)
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
        if ((Split-Path -Parent $resolvedWork) -eq $tempRoot -and
            (Split-Path -Leaf $resolvedWork) -match '^crypticnotes-package-[0-9a-f]{32}$') {
            Remove-Item -LiteralPath $resolvedWork -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
