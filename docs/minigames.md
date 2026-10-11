# 电脑端小游戏

点击布偶，在“小游戏”栏目下载、启动或删除“合成大水母”。首次下载包含游戏资源和独立运行组件，无需安装 Node.js。插件主包不包含这些资源，未启动游戏时也不加载 WebEngine。

游戏保留原项目 UI，在小于屏幕的置顶无边框窗口内运行。顶部窄栏可拖动，右上角叉号关闭，右下角可调整窗口大小。鼠标与方向键、回车保持原游戏操作。启动游戏会收起当前叠图；小游戏窗口不触发地图匹配快捷键。退出插件也会关闭小游戏。

下载包保存在用户数据目录的 `minigames/jellyfish`，音量偏好单独保存在 `minigame-saves/jellyfish`。删除包体保留音量偏好。插件版本更新不会删除小游戏包。下载在后台进行，验证 SHA-256 后安装；失败不替换已安装包。

## 开发与上架

当前已在 Windows 验证游戏画面、鼠标开始、回车投放、背景音乐和置顶窗口。Mac 使用相同接入代码及独立 `.app` 包，需要在 Mac 构建和签名后验证；未上架的系统会给出提示。

在项目根目录构建 Windows 可选包（不修改原小游戏目录）：

```powershell
.venv/Scripts/python.exe scripts/build_minigame.py --source "D:\学习资料\node.js\jellyfish"
```

输出到 `out/minigames/`，包括 `Jellyfish-windows-x64.zip` 和 `desktop-games.json`。只复制原项目的 `index.html`、`css`、`js`、`assets`，不包含录屏、测试截图或 `.git`。

检查包体：

```powershell
.venv/Scripts/python.exe scripts/publish_minigame.py
```

审阅完成后上传到 Jellyfish 仓库的独立 Release：

```powershell
.venv/Scripts/python.exe scripts/publish_minigame.py --publish
```

远端仓库必须已有 `main` 分支提交，才能创建 Release。插件下载 `https://github.com/HenryChen27/Jellyfish/releases/latest/download/desktop-games.json`，根据当前系统选择包体。包体和清单应一起上传；仅上传源码不能让“下载”按钮安装游戏。小游戏发布与插件发布独立，插件接入代码仍使用现有发布菜单打包。

重新打包前将 `out/minigames/windows-x64` 移到一个备份目录，构建脚本不会自动删除旧成品。更新游戏时同时修改 `--version` 和 `--tag`，例如 `--version 1.0.1 --tag desktop-v1.0.1`。

Mac 构建脚本支持 arm64/x64，但可选 `.app` 还需使用固定证书签名后再打包上架；不要直接分发未经签名和真机验证的 Mac 可选包。
