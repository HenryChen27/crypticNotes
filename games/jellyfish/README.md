# 合成大水母：插件适配

`overrides/` 是桌面和手机共用的游戏逻辑及界面。打包脚本先复制 Jellyfish 原项目，再应用这些文件；原项目音频、视频、图片和字体全部保留。

## 操作

- 点击“暂停”或按 Esc 暂停物理和声音，点击“继续游戏”恢复。
- “保存并退出”先写入存档，保存成功才关闭窗口；关闭窗口的 × 也会保存当前游戏。
- 再次启动时选择“继续上次游戏”或“开始新游戏”；新开一局会先确认替换存档。
- 对局结束自动记录本机个人排行榜，展示前 20 名。没有服务器、账号或成绩上传。
- 游戏中每 3 秒自动保存；窗口失焦、锁屏也会暂停。系统强制结束可能丢失最后几秒。
- 更新、删除游戏包保留存档；卸载 Android 应用会清除应用内存档。

## 存储

电脑存档在插件数据目录的 `minigame-saves/jellyfish/`。`local-storage.json` 使用原子替换，Windows 的 WebView2 也保留自身存储。

Android 存档在应用私有目录的 `minigame-saves/jellyfish/local-storage.json`，使用 AtomicFile。游戏包另存在 `minigames/jellyfish/`，从统一资源包按需下载，不增加 APK 的音视频体积。

Android 通过 `MiniGameOverlayService` 创建 TYPE_APPLICATION_OVERLAY 窗口，从布偶启动不会启动 Activity 或切换出游戏；需要已有的悬浮窗授权。运行期间通知栏显示小游戏服务状态。未开始采集时也可从应用的小游戏一栏启动。

## 构建与验证

```
.venv/Scripts/python.exe scripts/build_native_games.py --source "D:\学习资料\node.js\jellyfish"
.venv/Scripts/python.exe scripts/check_minigame_startup.py --native
.venv/Scripts/python.exe scripts/test_jellyfish_session.py
```

最后一项需要 `pip install playwright` 和系统 Edge，测试暂停不改变位置、存档恢复、合并中途存档以及个人排行去重。Android 悬浮操作需真机验收。
