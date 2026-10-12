# Windows 小游戏自动收起：本机实验

本次仅修改本机代码，没有打包或发布。

启动本机源码插件，在第五人格等待大厅打开合成大水母。检测绑定第五人格窗口，不截桌面，因此小游戏遮挡不会成为变化来源。找不到游戏窗口时不启用检测，小游戏页面显示原因。

约每 1.5 秒采样一次，缩小到 320×180 后去噪。先观察到稳定画面再启用判断；单像素颜色平均差超过 18 才计为明显变化，变化区域超过 25% 且平均颜色差超过 12 时触发。黑帧、窗口最小化和显著尺寸变化不会作为关键事件。

触发后最小化并静音，3 秒内双击布偶、点击水母或从任务栏恢复，会取消自动退出。否则启动器调用 safeSaveAndExit，保存成功并写入独立存档后关闭；保存失败恢复窗口提示重试。普通手动最小化不启动倒计时。小游戏关闭后释放检测会话。

样本测量在 out/game-scene-test/calibration.json。当前三张图中普通循环动画变化约 0.94%，匹配成功变化约 76.66%。它判断的是画面变化，不保证所有大厅、光效或其他弹窗都已覆盖；后续按真机反馈调整阈值。

本机依赖：pip install -r requirements-windows-capture.txt。

只编译启动器：python scripts/build_local_game_launcher.py。

验证：python -m unittest mapmatching.tests.test_game_scene_watch mapmatching.tests.test_game_background；python scripts/test_scene_window_capture.py；python scripts/test_game_auto_hide.py。
