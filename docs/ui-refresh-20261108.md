# 界面细化（2026-11-08）

按 `docs/ui-pet-review-20261108.md` 第二节实施，除第 6 点（叠图融入模式）外全部落地；
用户随后要求去掉「选项前的小图标」和「四角 L 形线」，已回退这两项，机制代码保留但不启用。

## 桌面端（PySide6）

- **键帽提示**（`line_icons.KeyCap`、`theme.paint_keycap`、`ui.keycap_text`）：
  「重新识别」「隐藏叠图」按钮右侧画出当前快捷键的小键帽；快捷键分组里每行的键名也改成键帽，
  长名称用短写（退格键→Back、空格→Space、方向键→Up/Down/Left/Right、鼠标侧键→侧键1/2）。
- **按下反馈**（`theme.ChalkButton`、`FoldSection.Heading`）：按下时整块下沉 1 px、粉笔面变暗，松开复原。
- **信息分层**（`ui.Companion.__init__` / `switch_module`）：「游戏设置」改为常开卡片（标题 + 手绘分隔线，
  含地图 / 地图版本 / 难度 / 路线 / 人数 / 重新识别 / 隐藏叠图），其余分组全部收进一个默认折叠的「更多」：
  地图设置、地图库、辅助设置、快捷键、应用更新；「界面设置」（字体、桌宠）仍是右上角齿轮页自己的内容，不进「更多」。版本有更新时红点同时打在「更多」和「应用更新」上。
- **手绘分隔线**（`theme.HandRule`）：卡片标题下一条微微起伏、两端渐隐的细线。
- **面板淡入**（`theme.reveal`）：打开设置面板 150 ms 淡入（布局托管的控件不做位移）。
- **分组命名与手机端统一**：问题排查→辅助设置，版本→应用更新；顺序 游戏设置 → 地图设置 → 地图库 → 辅助设置 → 界面设置 → 快捷键 → 应用更新。
- 保留但未启用：`line_icons.ICONS` 32 枚线稿图标与 `IconLabel`、`paint_worn_corners`（按用户要求不在选项前放图标、不画四角线）。

## 安卓端

- **按下反馈**（`Theme.ChalkButton.onDraw`）：按下时整块下沉 1 px（原有的变暗保留）。
- **手绘分隔线**（`Theme.HandRule`）：首页标题下的直线换成手绘线。
- **游戏内面板淡入**（`CaptureService` 打开快捷设置）：150 ms 淡入 + 6 dp 上浮。
- **气泡结果图标**（`CaptureService.setStatus`）：识别成功 ✓、失败 ?、换层/直接叠图用「楼层」图标，画在气泡文字前；
  其它提示不带图标。图标来自 `LineIcon.java`（由 `scripts/generate_line_icons_java.py` 从 `mapmatching/line_icons.py` 生成）。
- **识别中纹章转动**：由匀速旋转改为每圈三段 120°、段间短停的转动（1.5 s 一圈），更像游戏里的加载标。
- **帮助文字**：「?」弹出的说明字号 13 → 14（游戏字体 14 以下笔画发糊）；说明默认收起不变。
- 保留但未启用：`Theme.ChalkButton.setIcon`、`Theme.SectionHeading.setIcon`、`MistDrawable.drawWornCorners`。

## 验证

- 桌面：离屏构建 `Companion` 并截取面板（折叠/展开）；`test_ui_sync`、`test_ui_feedback`、`test_hotkey_choices`、
  `test_game_list_layout`、`test_pet*`、`test_lantern`、`test_minigames`、`test_map_manage_ui`、`test_preview` 通过；全套回归见本次汇报。
- 安卓：`assembleDebug` 通过，调试包装到 Xiaomi 15 Pro（`adb install -r`），首页截图核对；游戏内面板与气泡需在对局中人工确认。
