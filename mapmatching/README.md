> 2026-09-12 更新：已加入 Windows 齿轮悬浮 UI、G/Esc、默认 30% 原图叠加，并将困难、噩梦单人、噩梦多人地图统一迁入 `maps/`。双击根目录 crypticNotes.cmd，详见 [UI 使用说明](UI使用说明.md)。以下保留此前离线阶段的技术记录；当前仍会把叠图标为试用候选，真实噩梦截图还需要继续积累验证。

# Map Matching v2 — 模式约束匹配与离线叠图

已经跑通：明确模式 → 截图像素 → 局部候选检索 → Top-5 配准 → 楼层确认 → 离线叠图展示。
直接使用两套原始地图和 examples，旧 `plugin/` 代码、评分和缓存未进入新实现。

**[打开 6 张 example 叠图展示](../out/mapmatching/showcase/index.html)**：滑条对比原图/叠图，另有完整分辨率图片和逐图变换记录。

现有 6 张困难截图（4 张地图）在已知困难模式下最终第一候选和 floor 均为 6/6；41 个人工对应点初步测量，各图重投影 RMS 约 1.49–4.85 px，最大单点约 7 px。标注包含原图 2 px、截图 3 px 的估计点选误差，未做独立外部复核，不能据此声称亚像素精度或泛化能力。

当前提供**离线候选叠图**，没有游戏内透明悬浮窗/热键/自动跟踪。生产 decision 仍 UNKNOWN：缺少校准集和噩梦实测截图，尚不允许可靠自动 LOCK。预览命令明确展示候选，不把预览当已校准接受结果。

## 使用

仓库根目录运行，依赖见 requirements.txt：

```powershell
python -m mapmatching build-index
python -m mapmatching match examples/0/example.png --difficulty hard --output out/mapmatching/result.json
python -m mapmatching preview examples/0/example.png --difficulty hard --output out/mapmatching/preview.png
```

模式是用户开局前明确输入的条件，API/CLI 必须提供：困难 `--difficulty hard`；噩梦单人 `--difficulty nightmare --mode solo`；噩梦多人 `--difficulty nightmare --mode duo`。不从截图文件名或 example 配对标签填入模式。

`MapMatcher(index, difficulty=..., mode=...).match(bgr_pixels)` 只接受 uint8 BGR/BGRA 像素，不接受 GT 或 example ID。`MatchSession` 保留显式 rematch/unlock 生命周期；当前不产生 MATCHED/LOCK。

## 复现评估和展示

```powershell
python -m mapmatching.benchmarks.benchmark --difficulty hard --output out/mapmatching/known_hard_layout.json
python -m mapmatching.benchmarks.pose_evaluation --predictions out/mapmatching/known_hard_layout.json --output out/mapmatching/pose_layout.json
python -m mapmatching.benchmarks.showcase
python -m unittest discover -s mapmatching/tests -v
```

新 benchmark 不带 difficulty 参数时跑的是**全库**研究对照（当前 59 张：困难 28、噩梦单人 18、噩梦双人 13）；正常 matcher 强制明确模式。Nightmare 暂无 example，空评估结果不能报为通过。

## 坐标和数据边界

Pose 使用原始 reference **完整图**到原始**完整截图**坐标：`u=s*x+tx, v=s*y+ty`，rotation=0。楼层区域不会重置参考原点。

`maps/floors.json` 是**唯一的登记表**：哪张图参与匹配、它的楼层区域、插图/标题排除区和源文件 SHA256 都记在这里。内置原图与用户录入的图现在同在一张表里（以前是 `reference/floor_regions.json` 加一份单独的 `user_maps/`）。复核确认 Hard 各张均是 1F 在上、2F 在下，但分界位置不同；历史关于 Hard 上下反转的描述已被纠正。

`maps/` 里没有登记的图不参与匹配——这是「粘贴进目录不会被自动识别」和「新图走 UI 录入」这两条要求共用的同一条不变式。

索引使用 NPZ/JSON，禁用 pickle，校验 schema/config/layout hash；原图更新须重新审计和构建。只在请求的模式组加载数据。

`data/manual_landmarks.json` 仅供评估。预览重新执行推理后才附加评估标签，绝不使用人工点修正变换。显示清理（去字形假墙、保留原图路线/文字）不影响身份和位姿计算；当前 viewport 使用固定归一化布局先验。

当前报告见 [Progress](../out/mapmatching/progress_overlay.md)，历史 baseline/消融仍保存在 out/mapmatching。后续需扩充地图/楼层/zoom/fog 数据并校准拒识，再接游戏内显示层。
