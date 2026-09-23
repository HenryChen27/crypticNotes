# 加页手记地图插件的更新器（由同目录的 更新.cmd 调用）。
#
# 为什么逻辑不直接写在 .cmd 里：
#   cmd.exe 读批处理文件是按字节偏移定位下一行的，文件里一旦混入 GBK 中文，
#   偏移就会算错、跳到某一行中间开始执行（实测报「命令语法不正确」，
#   本该是 `where git >nul 2>nul` 的那行被从 `ul` 处截断）。
#   PowerShell 逐行按 Unicode 读，不存在这个问题。
#
# 为什么连「按任意键关闭」也放在这里：
#   控制台的输出代码页是进程间共享的，本脚本为了中文不乱码把它切到了 UTF-8；
#   等 PowerShell 退出后 cmd 再执行自己的 pause，它就会因为代码页对不上而退回英文提示。
#   索性由本脚本收尾，不把控制台交回给 cmd。

$ErrorActionPreference = 'Continue'

# 把控制台切到 UTF-8。不设的话，PowerShell 按控制台代码页（简体中文机器上是 GBK）
# 写自己的提示、而 git 写的是 UTF-8 字节，两种编码混在同一条输出流里互相打架，
# 结果总有一边是乱码。统一成 UTF-8 之后两边都对。
# 老系统上可能设不了，失败也不该让整个更新中断，所以吞掉异常。
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Set-Location (Split-Path -Parent $PSScriptRoot)

$repo   = 'https://github.com/HenryChen27/crypticNotes.git'
$branch = 'dist'

function Finish([int]$code) {
    Write-Host ''
    Write-Host '  按回车键关闭这个窗口... ' -NoNewline
    try { [void](Read-Host) } catch { }
    exit $code
}

Write-Host ''
Write-Host '  ============================================'
Write-Host '     加页手记地图插件 · 更新'
Write-Host '  ============================================'
Write-Host ''

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '  [错误] 这台电脑上没有找到 git。'
    Write-Host ''
    Write-Host '  这种更新方式需要先装一次 Git for Windows：'
    Write-Host '      https://git-scm.com/download/win'
    Write-Host ''
    Write-Host '  下载后一路点「下一步」装完，再双击 更新.cmd 就行。'
    Write-Host '  只需要装这一次，以后更新都不用再管它。'
    Finish 1
}

$first = -not (Test-Path '.git')

if ($first) {
    Write-Host '  [首次] 正在把这个文件夹接入更新通道...'
    Write-Host ''
    git init -q
    if ($LASTEXITCODE -ne 0) { Write-Host '  [错误] git init 失败。'; Finish 1 }
    git remote add origin $repo 2>$null
    git remote set-url origin $repo
    Write-Host '  [首次] 这一趟要下载约 230 MB，比以后每次的几 MB 多得多，'
    Write-Host '         请耐心等一会儿，中途不要关窗口。'
    Write-Host ''
} else {
    Write-Host '  [1/2] 正在检查有没有新版本...'
}

git fetch --depth 1 origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '  ============================================'
    Write-Host '     更新失败'
    Write-Host '  ============================================'
    Write-Host ''
    Write-Host '  常见原因：'
    Write-Host '    1. 网络连不上 github.com（校园网/公司网络有时会挡）'
    Write-Host '    2. 磁盘空间不足（更新要留出跟程序差不多大的空余）'
    Write-Host '    3. 杀毒软件或防火墙拦住了 git 联网'
    Write-Host ''
    Write-Host '  请把上面的报错信息截图发给 Henry。'
    Finish 1
}

Write-Host '  [2/2] 正在同步文件...'
$installRoot = (Get-Location).Path
$appPath = [IO.Path]::GetFullPath((Join-Path $installRoot 'IdentityVMapAssistant.exe'))
try {
    # Only stop processes whose executable belongs to THIS installation.
    $running = @(Get-Process -Name IdentityVMapAssistant -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $appPath })
    foreach ($appProcess in $running) { [void]$appProcess.CloseMainWindow() }
    if ($running.Count) {
        Write-Host '  正在退出当前目录的插件及识图进程...'
        Start-Sleep -Milliseconds 1200
    }
    $remaining = @(Get-Process -Name IdentityVMapAssistant -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path) -eq $appPath })
    foreach ($appProcess in $remaining) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction Stop
        Wait-Process -Id $appProcess.Id -Timeout 8 -ErrorAction SilentlyContinue
    }
    # Detect remaining locks or denied write access before touching any files.
    $tracked = @(git -c core.quotepath=false ls-files)
    $tracked += 'IdentityVMapAssistant.exe'
    foreach ($relative in ($tracked | Select-Object -Unique)) {
        $filePath = [IO.Path]::GetFullPath((Join-Path $installRoot $relative))
        if (-not $filePath.StartsWith($installRoot.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
            throw '更新路径越界'
        }
        if (Test-Path -LiteralPath $filePath -PathType Leaf) {
            $handle = [IO.File]::Open($filePath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
            $handle.Dispose()
        }
    }
} catch {
    Write-Host '  [错误] 程序文件仍被占用或没有写入权限，尚未开始替换文件。'
    Write-Host '  请退出插件；若插件以管理员运行，请用管理员身份运行更新.cmd。'
    Write-Host '  若仍失败，请重启电脑后先更新，不要先打开插件。'
    Write-Host ('  详细信息：'+$_.Exception.Message)
    Finish 1
}
$oldAskYesNo = $env:GIT_ASK_YESNO
$env:GIT_ASK_YESNO = 'false'
git checkout -f -q -B $branch FETCH_HEAD
$checkoutCode = $LASTEXITCODE
$env:GIT_ASK_YESNO = $oldAskYesNo
if ($checkoutCode -ne 0) { Write-Host ''; Write-Host '  [错误] 同步失败，请关闭插件后重新更新；不要启动未更新完整的程序。'; Finish 1 }

# 这里**刻意不跑 `git clean -fd`**。
# checkout 已经会删掉「上一版有、这一版没有」的受控文件，那才是版本更新该做的事；
# 而 clean 删的是**未跟踪**文件 —— 恰好就是朋友自己录入的地图原图
# （`add_map` 把它们复制进 maps/<难度>/，不属于发布内容）。删了没有第二份，找不回来。
# 代价只是旧版本遗留的垃圾文件会一直躺着，比丢用户的图划算得多。

Write-Host ''
Write-Host '  完成！当前版本：'
Write-Host ''
git --no-pager log --oneline -1
Finish 0
