# GitCode 国内下载仓库

仓库：https://gitcode.com/weixin_51917701/crypticNotes

当前阶段：三端新版客户端优先使用 GitCode 查询和下载主程序、地图库；GitHub 保留为过渡及查询回退渠道。发布脚本会自动同步完整国内快照、校验后更新 README。小游戏资源暂未迁移。

令牌保存在 Windows Git Credential Manager。脚本优先读取 GITCODE_TOKEN，其次读取 gitcode.com 对应的系统凭据。不要把令牌放进仓库、命令行参数、JSON配置或日志。

本地仓库检出目录为 release/gitcode，与 release/crypticNotes 独立。

检查账户、分支及 Release：

    .venv\Scripts\python.exe scripts\gitcode_release.py status

校验本次两批成品并生成上传计划（不上传）：

    .venv\Scripts\python.exe scripts\gitcode_release.py plan --jobs release\jobs\20261030-165124\release-job.json release\jobs\20261030-185229\release-job.json

非敏感配置：scripts/gitcode_release.json。client_updates_enabled 记录国内通道启用状态，不是客户端设置开关；mirror_after_github_publish=true 表示发布菜单自动同步 GitCode。旧客户端需安装一次过渡更新。

安装包与地图库已接入 GitCode，小游戏暂用原仓库，不能只迁移清单而缺少包体；包体复用现有构建并核对SHA-256，不重新签名或无故升版本。

GitCode官方文档：
- 认证：https://docs.gitcode.com/en/docs/guide/
- 创建Release：https://docs.gitcode.com/docs/apis/post-api-v-5-repos-owner-repo-releases/
- 上传附件：https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-releases-tag-upload-url/

上传接口与 GitHub 不同：先取得上传地址，再向返回的地址发PUT，只发送接口返回的存储头，不携带GitCode令牌。上传完成后还会匿名下载并检查大小及 SHA-256，全部一致才转为正式版本。

## 云端镜像

release/gitcode/.gitcode/workflows/mirror-release.yml 使用 GitCode 自带 Runner，通过官方 GitHub 资产接口只读下载现有发布附件，核对 scripts/artifacts.json 后上传。

流水线只有仓库读取权限，不调用发布 API。由本机使用系统凭据取得本次指定附件的临时上传地址，通过手动运行输入 upload_plan 传给流水线；个人令牌不提交到云端。传输后由本机匿名下载核对并完成正式发布。临时地址不得写入仓库或打印到日志。已存在且校验一致的附件会复用，冲突文件拒绝覆盖。

仅本地上传时：

    python scripts/gitcode_release.py publish --jobs release/jobs/20261030-165124/release-job.json release/jobs/20261030-185229/release-job.json --tag v2026.10.30

## 客户端接入

三端主程序更新与地图库查询已接入公开 GitCode latest Release API，不需要用户令牌。查询失败时回退原 GitHub API；下载仅接受两个官方仓库的附件地址。

地图库清单中的 URL 会按同一 Release 的真实附件地址解析，且必须先匹配大小、SHA-256，避免清单已迁移而包体仍走 GitHub，或读取到半次发布的数据。地图识别逻辑和个人地图保存方式不变。小游戏资源尚未迁移，仍走原小游戏仓库。

源码修改需要重建安装包才能影响已安装客户端。旧版仍查询 GitHub，迁移应提供一个过渡版本或让用户从 GitCode 手动安装。

## 过渡版本之后的发布

scripts/gitcode_release.json 的 mirror_after_github_publish=true 已接入发布菜单：GitHub 成功校验后，自动同步 GitCode 完整快照、匿名下载校验并更新国内 README。只选一个平台也会保留其他平台的附件；不必给未改动的平台升版本。

GitCode 同步失败时，GitHub 已完成部分不会撤销；用原批次 --resume 重试，不重新打包。独立重试国内同步：

    .venv\Scripts\python.exe scripts/gitcode_cloud_release.py --jobs release/jobs/批次/release-job.json --tag v日期-批次时间 --github-snapshot

必须沿用失败时打印的 GitCode tag，才能跳过已传好的附件。云端仅收到指定附件的临时上传地址；不保存个人令牌、不授予项目写入权限。
