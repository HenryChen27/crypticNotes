# 合成大水母：插件适配

游戏内容以 Jellyfish 原项目为准。打包脚本原样复制 `index.html`、`js/`、`css/` 和 `assets/`，不再应用 `overrides/` 中的旧逻辑或添加界面。音视频、图片和字体保持原文件；原项目删除的资源也不会残留在新包中。

2026-10-12：原项目已自带存档、排行榜及结算界面，下面的操作说明仅描述旧适配版本，不作为当前原项目行为的承诺。`overrides/` 暂时保留用于回退，不参与打包。

## 构建

运行 scripts/build_native_games.py --source 指向 Jellyfish 原项目目录。生成的统一游戏资源包是 out/minigames-native/Jellyfish-game.zip。

本地安装位于 minigames/jellyfish。原项目的 tests 不进入发布包；根目录录屏文件也不进入发布包。

插件保留按需下载、删除和启动入口，游戏玩法、界面和存档均由原项目实现。
