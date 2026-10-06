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

function Copy-WithRetry([string]$Source, [string]$Destination) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Destination -Force
            return
        } catch [IO.IOException] {
            if ($timer.Elapsed.TotalSeconds -ge 15) { throw }
            Start-Sleep -Milliseconds 250
        } catch [UnauthorizedAccessException] {
            if ($timer.Elapsed.TotalSeconds -ge 15) { throw }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Merge-MapLibrary([string]$Payload, [string]$OldMaps, [string]$NewMaps) {
    $mergeExe = Resolve-Child $Payload 'IdentityVMapAssistant.exe'
    $mergeArgs = '--merge-map-update "' + $OldMaps + '" "' + $NewMaps + '"'
    $mergeProcess = Start-Process -FilePath $mergeExe -ArgumentList $mergeArgs -WindowStyle Hidden -Wait -PassThru
    if ($mergeProcess.ExitCode -ne 0) { throw '地图库合并失败，已保留原地图库，请检查用户地图是否重名或损坏' }
}

function Install-Payload([string]$Payload, [string]$Destination, [string]$Backup) {
    # Merge user maps into the staged library before replacing any live files.
    # Settings/records live in LOCALAPPDATA and are not touched here.
    $changed = [Collections.Generic.List[object]]::new()
    $payloadMaps = Resolve-Child $Payload 'maps'
    $targetMaps = Resolve-Child $Destination 'maps'
    $savedMaps = Resolve-Child $Backup 'maps'
    $hadMaps = Test-Path -LiteralPath $targetMaps -PathType Container
    $mapsInstalled = $false
    try {
        if (Test-Path -LiteralPath $payloadMaps -PathType Container) {
            if (Test-Path -LiteralPath $targetMaps -PathType Leaf) { throw '目标 maps 被同名文件占用' }
            Merge-MapLibrary $Payload $targetMaps $payloadMaps
            if ($hadMaps) {
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $savedMaps))
                Move-Item -LiteralPath $targetMaps -Destination $savedMaps
            }
            $mapsInstalled = $true
            Copy-Item -LiteralPath $payloadMaps -Destination $targetMaps -Recurse
        }
        foreach ($file in Get-ChildItem -LiteralPath $Payload -File -Recurse) {
            $relative = $file.FullName.Substring($Payload.TrimEnd('\').Length + 1)
            if ($relative -match '^(maps|out|records|\.git)(\\|$)' -or $relative -eq '.windows-update.json') { continue }
            $target = Resolve-Child $Destination $relative
            $saved = Resolve-Child $Backup $relative
            if (Test-Path -LiteralPath $target -PathType Container) { throw '目标文件被同名目录占用' }
            $existed = Test-Path -LiteralPath $target -PathType Leaf
            if ($existed) {
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $saved))
                Copy-WithRetry $target $saved
            }
            $changed.Add(@{Target=$target; Saved=$saved; Existed=$existed})
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
            Copy-WithRetry $file.FullName $target
        }
    } catch {
        $failure = $_
        $rollbackErrors = @()
        for ($i=$changed.Count-1; $i -ge 0; $i--) {
            $entry = $changed[$i]
            try {
                if ($entry.Existed) { Copy-WithRetry $entry.Saved $entry.Target }
                elseif (Test-Path -LiteralPath $entry.Target -PathType Leaf) { Remove-Item -LiteralPath $entry.Target -Force }
            } catch { $rollbackErrors += $_.Exception.Message }
        }
        try {
            if ($mapsInstalled -and (Test-Path -LiteralPath $targetMaps -PathType Container)) {
                Remove-Item -LiteralPath $targetMaps -Recurse -Force
            }
            if ($hadMaps -and (Test-Path -LiteralPath $savedMaps -PathType Container)) {
                Move-Item -LiteralPath $savedMaps -Destination $targetMaps
            }
        } catch { $rollbackErrors += $_.Exception.Message }
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

# A bare MessageBox can land behind the game or editor exactly like the main
# window did, so give it an invisible topmost owner: an owned dialog inherits
# TopMost from its owner and is guaranteed to be the one the user sees.
function New-NoticeOwner {
    $owner = [Windows.Forms.Form]::new()
    $owner.FormBorderStyle = 'None'
    $owner.ShowInTaskbar = $false
    $owner.StartPosition = 'CenterScreen'
    $owner.Size = [Drawing.Size]::new(1,1)
    $owner.Opacity = 0
    $owner.TopMost = $true
    $owner.Show()
    return $owner
}

function Show-Notice([string]$Text) {
    $owner = New-NoticeOwner
    try { [void][Windows.Forms.MessageBox]::Show($owner,$Text,'加页手记 · 更新','OK','Information') }
    finally { $owner.Dispose() }
}

# Being up to date is not a reason to refuse. Players delete files by accident,
# and a half-removed install looks exactly like a broken plugin, while
# re-installing the whole package is the only repair path this app has. So ask
# instead of refusing -- but default to 否 (Button2), so a stray Enter cannot
# start a 240MB download on its own.
function Confirm-Redownload {
    $owner = New-NoticeOwner
    try {
        $message = "当前已经是最新版本。`n`n仍然重新下载并覆盖安装一次吗？`n`n如果插件文件被误删、或运行不正常，选「是」可以完整修复（会重新下载整个安装包）。"
        $answer = [Windows.Forms.MessageBox]::Show($owner,$message,'加页手记 · 更新','YesNo','Question','Button2')
        return $answer -eq [Windows.Forms.DialogResult]::Yes
    } finally { $owner.Dispose() }
}

$mutexKey = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($InstallRoot.ToLowerInvariant())).Replace('\','_').Replace('/','_')
$mutex = [Threading.Mutex]::new($false, ('Local\CrypticNotesUpdate-' + $mutexKey))
$locked = $false
try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
# Never exit silently here. The window holding this mutex is usually still open
# somewhere behind the game (it stays until the user clicks 关闭), so a silent
# exit made the update button look dead: no window, no message, nothing in the
# log. Say what is actually wrong instead.
if (-not $locked) {
    Show-Notice "更新器已经在运行。`n`n请先找到标题为「加页手记 · 更新」的窗口并关闭它，然后再点一次更新。"
    exit
}
$form = [Windows.Forms.Form]::new()
$form.Text = '加页手记 · 更新'
$form.ClientSize = [Drawing.Size]::new(440,190)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
# The plugin overlays a fullscreen game and the user may have an editor in front
# of that. Without TopMost this window opened behind both, so a perfectly
# successful update looked like the button had done nothing.
$form.TopMost = $true
$form.BackColor = [Drawing.Color]::FromArgb(37,55,69)
$form.ForeColor = [Drawing.Color]::FromArgb(224,235,242)
$form.Font = [Drawing.Font]::new('Microsoft YaHei UI',10)
$label = [Windows.Forms.Label]::new()
$label.SetBounds(22,18,396,92)
$label.Text = '正在检查更新…'
$bar = [Windows.Forms.ProgressBar]::new()
$bar.SetBounds(22,118,396,12)
$bar.Style = 'Marquee'
$button = [Windows.Forms.Button]::new()
$button.SetBounds(308,146,110,30)
$button.Text = '取消'
$button.FlatStyle = 'Flat'
$button.Add_Click({ $form.Close() })
$form.Controls.AddRange(@($label,$bar,$button))
$form.Show()
[void]$form.Activate()
$work = Join-Path ([IO.Path]::GetTempPath()) ('crypticnotes-package-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($work)
$client = [Net.WebClient]::new()
$client.Headers['User-Agent'] = 'CrypticNotes-Windows-Updater'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$completed = $false
$logRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'IdentityVMapAssistant\out'
[void][IO.Directory]::CreateDirectory($logRoot)
$logPath = Join-Path $logRoot 'updater.log'
function Log([string]$Message) {
    ('{0:yyyy-MM-dd HH:mm:ss.fff}  {1}' -f [DateTime]::Now,$Message) | Add-Content -LiteralPath $logPath -Encoding UTF8
}
Log "start installRoot=$InstallRoot"

function New-Client {
    $fresh = [Net.WebClient]::new()
    $fresh.Headers['User-Agent'] = 'CrypticNotes-Windows-Updater'
    return $fresh
}

# WebClient wraps every failure in one generic WebException whose Message is
# useless to the user. Walk down to the real cause so the dialog says what
# actually happened instead of the wrapper.
function Explain($Exception) {
    # A failed download arrives as MethodInvocationException (PowerShell wrapping
    # .GetResult()) around WebException around the real IOException, so the outer
    # two messages are pure noise: "使用"0"个参数调用"GetResult"时发生异常". Walk to
    # the deepest cause instead.
    $node = $Exception
    $web = $null
    while ($node) {
        if (-not $web -and $node -is [Net.WebException]) { $web = $node }
        if (-not $node.InnerException) { break }
        $node = $node.InnerException
    }
    $text = '' + $Exception.Message
    if ($Exception -is [Management.Automation.MethodInvocationException] -or $Exception -is [Net.WebException]) {
        if ($node.Message) { $text = '' + $node.Message }
    }
    if ($web -and $web.Status -and $web.Status -ne [Net.WebExceptionStatus]::UnknownError) { $text = "$text（$($web.Status)）" }
    $text = $text.Trim()
    if ($text.Length -gt 62) { $text = $text.Substring(0,62) + '…' }
    if (-not $text) { $text = '未知错误，详见日志' }
    return $text
}

function Download([string]$Url, [string]$Path, [long]$Size = 0, [int]$Attempts = 4) {
    if (-not $Url.StartsWith('https://github.com/HenryChen27/crypticNotes/releases/download/')) { throw '更新地址不是项目官方发布地址' }
    # GitHub release assets answer Range requests with 501, so an interrupted
    # 230 MB download cannot be resumed. Retry the whole file rather than
    # dropping the user back to a manual reinstall.
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        if ($attempt -gt 1) {
            $label.Text = "网络中断，正在重试 $attempt/$Attempts…"
            $bar.Style = 'Marquee'
            [Windows.Forms.Application]::DoEvents()
            Start-Sleep -Seconds (2 * ($attempt - 1))
        }
        if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue }
        $client = New-Client
        try {
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
                    $label.Text = ('正在下载 {0:N1} / {1:N1} MB（第 {2}/{3} 次）' -f ($bytes/1MB),($Size/1MB),$attempt,$Attempts)
                }
                Start-Sleep -Milliseconds 80
            }
            $task.GetAwaiter().GetResult()
            return
        } catch {
            if ($form.IsDisposed -or $_.Exception.Message -eq '已取消更新') { throw }
            Log "download $attempt/$Attempts failed: $($_.Exception.ToString())"
            if ($attempt -eq $Attempts) { throw }
        } finally {
            $client.Dispose()
        }
    }
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
    Log "release=$($release.tag_name) assets=$($release.assets.Count)"
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
    # 已经是最新版本也照样问一句：自建地图用户误删过文件时，重装一遍是唯一的修复途径。
    $redownload = $sameBuild -or ($installed -and $installed.sha256 -eq $expected)
    if ($redownload -and -not (Confirm-Redownload)) {
        $label.Text = '已经是最新版本'
    } else {
        # The zip and the extracted tree both live in %TEMP%; a full disk used to
        # surface as "WebClient 请求期间发生异常" somewhere around 90%.
        $volumeRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($work))
        $needed = [long]$asset[0].size * 2 + 256 * 1MB
        $free = ([IO.DriveInfo]::new($volumeRoot)).AvailableFreeSpace
        if ($free -lt $needed) {
            throw ('磁盘空间不足：本次更新需要约 {0:N0} MB，{1} 只剩 {2:N0} MB，请清理后重试' -f ($needed/1MB),$volumeRoot,($free/1MB))
        }
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
        if ($running.Count) { Start-Sleep -Milliseconds 1800 }
        foreach ($process in @(Get-Process -Name IdentityVMapAssistant -ErrorAction SilentlyContinue | Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $appPath })) {
            # Python's matching worker is a child process. Killing only the UI
            # can leave that child holding package/map files long enough for
            # replacement to fail. taskkill /T scopes the cleanup to this app's
            # process tree and does not touch another installation.
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            Wait-Process -Id $process.Id -Timeout 8 -ErrorAction SilentlyContinue
        }
        Install-Payload $payload $InstallRoot (Join-Path $work 'backup')
        @{sha256=$expected} | ConvertTo-Json | Set-Content -LiteralPath $stampPath -Encoding UTF8
        $label.Text = if ($redownload) { '已重新下载并完整覆盖安装，插件文件已恢复为发布版。' }
                      else { '更新完成，设置已保留，地图库已同步到最新版。' }
        Start-Process -FilePath $appPath -WorkingDirectory $InstallRoot -WindowStyle Hidden
        Log "success sha256=$expected"
    }
    $bar.Style = 'Continuous'
    $bar.Value = 100
    $completed = $true
} catch {
    Log "failure $($_.Exception.ToString())"
    if (-not $form.IsDisposed) { $label.Text = "更新未完成：$(Explain $_.Exception)`n日志：$logPath" }
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
