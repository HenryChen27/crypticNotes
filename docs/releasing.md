# 自己打包与发布

## 最方便的入口

在开发电脑上双击 `scripts/release-menu.cmd`，不需要输入参数。先选择“只打包”“打包并发布”或“上传已有包 / 重试发布”，再按提示选择平台。上传重试可以直接选择已有批次编号，不需要复制命令。输入 0 退出。

- 1：Windows。
- 2：Android。
- 3：Mac，自动构建 Apple Silicon 和 Intel 两版。
- 4：全部。

包体与校验记录保存在 `release/jobs/日期-时间/`，不同批次不会互相覆盖。控制台最后会打印目录和失败重试命令。工具维护现有最新 GitHub Release 的指定平台附件，未选择的平台不会删除或替换。

## 命令行

发布之前更新 `mapmatching/assets/update-news.json`：`changes` 是两端共用的更新条目，`android` 是可选的手机端条目，`important` 是可选的红色提醒。新一期公告请换 `id`，不要改设置迁移键。公告打进主程序，不联网也能显示；同一个安装版本只弹一次。命令行的 `--notes` 用于发布页正文。PVP 资源包由 `scripts/build_pvp_package.py` 生成，发布批次会一起上传 `IdentityVMapAssistant-PVP.zip`；APK 和桌面主包不应包含这些资源。

以下参数仅供自动化使用，日常双击 CMD 操作即可。

在项目根目录的 PowerShell 中运行：

```powershell
# 只打包 Android，不上传
.venv\Scripts\python.exe scripts\release_manager.py --platforms android

# Windows 和 Android 正式候选：只在本机打包，从弹窗公告生成同文发布说明，不上传
.venv\Scripts\python.exe scripts\release_manager.py --platforms windows android --notes mapmatching\assets\update-news.json

# 打包并发布 Windows 和 Android
.venv\Scripts\python.exe scripts\release_manager.py --platforms windows android --publish

# 全平台，附上自己写的 UTF-8 更新公告
.venv\Scripts\python.exe scripts\release_manager.py --platforms all --publish --notes out\本次更新.md

# 上传失败后，用该批次的文件重试；不会重新加版本或重新打包
.venv\Scripts\python.exe scripts\release_manager.py --resume release\jobs\日期-时间\release-job.json
```

`--resume` 会真正发布，不是预览。仅可用于已经完成构建并生成 `release-job.json` 的批次。正式发布前会校验文件没有被修改，并拒绝覆盖更高的已发布版本。

## 玩家灰度：两个下载链接，有效期 24 小时

灰度不走发布菜单，不改正式更新清单。Windows 用 `scripts/build_windows.py --preview-dir out/gray/<批次>` 生成独立 ZIP。安卓先准备 `release/IdentityVMapAssistant-PVP.zip` 并运行 `scripts/prepare_android.py`。用 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 为资源生成一次性随机路径，再用项目 Gradle 工具链运行 `assembleRelease -PgrayLabel=<日期.序号> -PgrayPvpToken=<随机路径>`。APK 固定本批资源的 HTTPS 地址、大小和 SHA-256，保留原签名和 versionCode；正式构建不给这两个参数，仍从正式发布附件取包。

仅修安卓时，使用全新的私有目录，放入 `IdentityVMapAssistant-Android-arm64-gray.<日期.序号>.apk` 和 `IdentityVMapAssistant-PVP.zip`。上传核对后运行 `gray_downloads.py issue <目录> https://smgfxyjq.cfd --android-label <日期.序号> --pvp-token <同一随机路径>`。用 `gray_caddy.py` 为这次签发生成两条精确匹配的路径，在已有域名配置中引入并验证；二者共用 24 小时截止时间。不要覆盖、续期或重新签发上轮安卓和 Windows 链接。

两端一起更新时，把带灰度编号的 APK、`IdentityVMapAssistant-Windows-x64.zip`、`IdentityVMapAssistant-PVP.zip` 都放进同一个新的服务器私有目录。核对三个文件的 SHA-256 后，在上述带 `--android-label` 和 `--pvp-token` 的签发命令末尾加 `--include-windows`。三条路径共用一个新的 24 小时窗口；只向玩家分享 APK 和 Windows ZIP，PVP 由应用按需下载。旧批次保留原截止时间。

如果只分发不带灰度编号的 APK 和 Windows ZIP，可使用不带参数的双文件模式：文件名为 `IdentityVMapAssistant-Android-arm64.apk` 与 `IdentityVMapAssistant-Windows-x64.zip`。所有模式的目录都必须在静态根目录之外，不要另设永久直链。

- 将下载域名的 `/jysj-gray/` 配置为 HTTPS 反向代理，保留完整路径，转发至本机专用端口。关闭该路径的代理/CDN 缓存和含链接的访问日志。
- **准备好分享时才签发**：在服务器上运行 `python3 gray_downloads.py issue <私有目录> <HTTPS源站>`。它返回两条不同的随机链接，以及同一个 UTC 截止时间。用 `python3 gray_downloads.py serve <私有目录> --port <专用端口>` 在回环地址提供下载。重复签发或重启不会刷新时间。
- 分享前从外网匿名下载两个文件并核对 SHA-256，同时确认没有不经校验的静态入口。可在独立测试批次验证过期行为，不修改生产服务器时间。到点后新的下载、HEAD 和续传都返回 410；已下载到玩家设备的文件不受影响。

## 自动完成的步骤

升版本之前先按平台比较源码、地图、资源及构建配置的内容指纹。没有变化且历史包校验一致的平台，会跳过升版本、打包和上传；全部一致时直接结束。Android 不会因为桌面 UI 修改而更新，共享匹配核心或地图变化则会影响多个平台。自动版本号、文件时间、编译缓存不参与判断。

发布时读取 GitHub Release 的各平台 `*-inputs.json`，并验证它记录的正式包校验值；只打包时比较本地已成功构建的批次。未上传的本地包不会被当成已发布版本。旧发布包没有内容记录，**第一次使用新机制可能需要构建并发布一次以建立基线**；脚本会提示原因。不能仅凭旧包版本号断定源码相同。记录缺失或包被替换时也不会误判为无需更新。

内容指纹用于判断受管理的发布输入是否变化，不是跨机器二进制可重复构建证明；更换本地 SDK、Python 或依赖环境后，应清理对应历史基线并重新验证构建。

1. Android 的 versionCode 自动取本地和已发布版本的较大值再加一；versionName 的补丁号加一。只打本地包时只参考本地版本。预览版后缀保留。
2. Windows 沿用构建时间戳版本，不需要手改版本号。
3. Mac 自动提高 `macos-version.json` 的补丁版本和构建号，在签名前写入应用 Info.plist。
4. 发布或构建 Mac 时，把开发仓库已跟踪的产品源码与地图同步到 `release/crypticNotes`，提交并推送到远端默认分支。只允许快进，遇到远端分歧或公共检出目录有未提交修改会停止，不强推。新建的源码文件请先在开发仓库 `git add`，否则无法被同步。开发仓库里不再跟踪的文件（删除或 `git mv` 搬走的地图）会同步从公共仓库移除，公共树始终等于开发仓库当前跟踪的产品文件。
5. Windows 构建后运行成品匹配冒烟测试；Android 验证 APK 签名仍是当前已发布证书；Mac 触发现有 GitHub Actions，等待两个架构构建、签名、启动测试通过，下载并校验包体。
6. 先上传临时附件并核对 GitHub SHA-256，全部成功后才替换正式附件，更新清单最后切换。中途替换阶段仍不是服务器事务；失败时用 `--resume` 完成。公告追加在 Release 顶部，原有说明保留。

失败构建不会撤回已经增加的版本号，允许跳号；重新运行会使用下一个版本。不要同时运行旧发布脚本或其他发布任务。异常断电留下 `out/release-manager.lock` 时，确认没有运行中的发布进程后再删除该锁文件。

## 这台开发电脑的前提

- 使用项目 `.venv` 的 Python，已经安装构建依赖；需要 Git，但最终用户不需要 Git。
- Git Credential Manager 已登录 GitHub，或通过环境变量设置 `GH_TOKEN` / `GITHUB_TOKEN`，具备仓库写入和 Actions 权限；不要把令牌写进脚本。
- `release/crypticNotes` 是现有公开仓库的独立检出目录。新电脑先运行 `git clone https://github.com/HenryChen27/crypticNotes.git release/crypticNotes`。
- Android 使用当前 `out/android-tools` 下的 JDK、Gradle、SDK、Python 3.10，以及 `android/local.properties`。换电脑要迁移这些工具/配置和原签名密钥，不能用新生成的 debug 密钥覆盖旧用户安装。脚本会检查已发布证书指纹。
- Mac 在 GitHub 构建，不需要本机有 Mac。仓库已有 `MACOS_SIGNING_P12`、`MACOS_SIGNING_P12_PASSWORD` 两项签名 Secret；不能删除或换成临时签名。即使不加 `--publish`，选择 Mac 也会推送源码并使用 Actions，只是不更新 Release。
- 脚本面向这套已配置好的 Windows 开发工作区，不负责自动安装整套工具链。公共检出的 Mac 工作流沿用远端版本，不用本地旧副本覆盖签名工作流。

## 地图库与旧分发分支

三个平台构建均读取当前 `maps`。修改地图后再运行入口即可。Windows 的旧更新器首次过渡仍应遵循 [地图库更新说明](map-library-updates.md)，不要直接覆盖用户自建地图。

新客户端优先从 GitCode Release 检查及下载主程序和地图库，查询连接失败时回退 GitHub，不再从 `dist` 分支更新。发布脚本完成 GitHub 过渡发布后，会自动按 [GitCode 发布说明](gitcode-releasing.md) 同步国内完整附件、校验并标记为 latest。GitCode 同步失败时可用原批次重试，不重新打包或升版本。旧客户端仍查询 GitHub，需要过渡版或手动安装。`dist` 分支删除前保留归档标签；这不删除本地 `dist/` 构建目录或 Release 附件。极老的依赖 Git 分支更新的客户端需手动下载当前 Release。
