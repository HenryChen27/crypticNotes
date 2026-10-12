# 合成大水母：插件适配

游戏内容以 Jellyfish 原项目为准。打包脚本原样复制 `index.html`、`js/`、`css/` 和 `assets/`，不再应用 `overrides/` 中的旧逻辑或添加界面。音视频、图片和字体保持原文件；原项目删除的资源也不会残留在新包中。

`overrides/` 暂时保留用于回退，不参与打包。原项目自带的存档、排行榜及结算界面原样保留。

## 窗口控制与安全关闭

启动器顶部提供全屏、恢复窗口和隐藏。Windows 可从托盘重新显示，Mac 可从菜单栏重新显示，安卓可从“水母”恢复按钮重新显示。隐藏只是收起窗口，不等于关闭游戏。

关闭按钮调用 `await window.JellyfishGame.safeSaveAndExit()`。启动器等待 `saved` 为真，再将 `jellyfish.*` 本地存储原子写入独立存档目录，最后关闭并释放窗口。保存失败或超时不会退出。原游戏自己的退出按钮仍按原项目返回初始化界面。

`scripts/game_launcher/safe-exit.js` 仅负责宿主通信，不修改游戏源码或增加游戏界面；安卓使用同内容的 assets 文件。

## 构建

运行 scripts/build_native_games.py --source 指向 Jellyfish 原项目目录。生成的统一游戏资源包是 out/minigames-native/Jellyfish-game.zip。

本地安装位于 minigames/jellyfish。原项目的 tests 不进入发布包；根目录录屏文件也不进入发布包。

插件保留按需下载、删除和启动入口，游戏玩法、界面和存档均由原项目实现。

验证命令：`python scripts/test_game_host_bridge.py`、`python scripts/check_minigame_startup.py --native`。原项目的 `tests/save_check.py` 可在打包输出的游戏副本上运行。
