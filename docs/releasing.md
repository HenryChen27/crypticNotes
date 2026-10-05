# 自己打包与发布

## 最方便的入口

在开发电脑上双击 `scripts/release-menu.cmd`，输入平台编号（可以空格分隔选择多个），再选择是否发布。

- 1：Windows。
- 2：Android。
- 3：Mac，自动构建 Apple Silicon 和 Intel 两版。
- 4：全部。

包体与校验记录保存在 `release/jobs/日期-时间/`，不同批次不会互相覆盖。控制台最后会打印目录和失败重试命令。工具维护现有最新 GitHub Release 的指定平台附件，未选择的平台不会删除或替换。

## 命令行

在项目根目录的 PowerShell 中运行：

```powershell
# 只打包 Android，不上传
.venv\Scripts\python.exe scripts\release_manager.py --platforms android

# 打包并发布 Windows 和 Android
.venv\Scripts\python.exe scripts\release_manager.py --platforms windows android --publish

# 全平台，附上自己写的 UTF-8 更新公告
.venv\Scripts\python.exe scripts\release_manager.py --platforms all --publish --notes out\本次更新.md

# 上传失败后，用该批次的文件重试；不会重新加版本或重新打包
.venv\Scripts\python.exe scripts\release_manager.py --resume release\jobs\日期-时间\release-job.json
```

`--resume` 会真正发布，不是预览。仅可用于已经完成构建并生成 `release-job.json` 的批次。正式发布前会校验文件没有被修改，并拒绝覆盖更高的已发布版本。

## 自动完成的步骤

1. Android 的 versionCode 自动取本地和已发布版本的较大值再加一；versionName 的补丁号加一。只打本地包时只参考本地版本。预览版后缀保留。
2. Windows 沿用构建时间戳版本，不需要手改版本号。
3. Mac 自动提高 `macos-version.json` 的补丁版本和构建号，在签名前写入应用 Info.plist。
4. 发布或构建 Mac 时，把开发仓库已跟踪的产品源码与地图同步到 `release/crypticNotes`，提交并推送到远端默认分支。只允许快进，遇到远端分歧或公共检出目录有未提交修改会停止，不强推。新建的源码文件请先在开发仓库 `git add`，否则无法被同步。删除源码文件会停止，需先明确处理公共仓库的对应删除。
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

现行客户端从 GitHub Release 下载包，不再从 `dist` 分支更新。`dist` 分支删除前保留归档标签；这不删除本地 `dist/` 构建目录或 Release 附件。极老的依赖 Git 分支更新的客户端需手动下载当前 Release。
