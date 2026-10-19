# 小游戏仓库与桌面模块

小游戏仓库：https://github.com/HenryChen27/mini_games

水母位于 games/jellyfish，蚀骨赠礼位于 games/minesweeper。PC 游戏页启动时和打开页签时在后台读取 Release 附件 games.json，动态列出游戏。源码根目录 games.json 是构建输入，格式不同，不能当下载清单。

客户端仍读取 native-desktop-games.json 中的共用启动器信息。各游戏独立安装到 minigames/<id>，存档独立保存到 minigame-saves/<id>。下架游戏不会被自动删除；本地已安装项仍保留。删除游戏不删存档。更新标记按内容 SHA-256 判断；下载时重新查询远程清单。

游戏声音、画面变化自动收起及快捷键保存于 out/minigames/preferences.json。快捷键默认不设置，避免抢占游戏按键。公共启动器新增声音与显示命令和蚀骨赠礼保存接口后，需要单独重新发布启动器附件；只更新插件不能替换旧公共启动器。

PC 加页手记识图模块包为 IdentityVMapAssistant-Matching.zip，清单为 matching-module.json，发布在 crypticNotes 仓库。公共程序保留共用 Python/Qt 运行环境与代码，官方地图库负载不再随 Windows 基础包携带。没有模块时不会启动识图进程。首次下载、检查更新在后台完成，地图合并沿用个人地图保护逻辑。卸载保留个人数据到 module-user-data/mapmatching，源码开发环境不会删除工程 maps；旧版来源不明的文件按个人数据保守保留。

未来要进一步拆除基础包中的科学计算依赖，需要再把识图引擎做成独立进程运行包；当前分包不承诺完整去掉这些共用运行库。

合集资源使用 mini_games 的 scripts/package_release.py 和 scripts/publish_release.ps1。旧单游戏发布脚本不能直接用于合集，避免覆盖 games.json 或让清单不一致。

本次尚未发布。正式发布前要同时生成识图模块包与清单，并发布新版公共小游戏启动器。
