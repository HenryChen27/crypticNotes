# 性能分析（2026-11-06，仅分析，未改代码）

目标：在不改变识图判定、叠图结果和交互行为的前提下，减少手机与电脑端的常驻 CPU/GPU 开销。本文按「平台 → 场景（待机 / 开图 / 小游戏）」整理，每条给出位置、原因、方案和风险等级。

风险等级：
- **A 零行为变化**：输出像素/判定数值完全一致，只是少做无用功。
- **B 观感或时序微调**：动画帧率、延迟 ≤100 ms 等，判定逻辑不变。
- **C 影响判定输入**：会改变送入门控/匹配的像素或阈值环境，需要真机/实机回归。

---

## 一、电脑端（Windows 为主，macOS 顺带）

### 1. 待机时就在跑的常驻开销

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| 1.1 | `mapmatching/mouse_input.py:149-185`、`keyboard_input.py:84,97-119` | Raw Input 用 `RIDEV_INPUTSINK` 订阅鼠标和键盘，**每次鼠标移动**都产生 WM_INPUT；鼠标、键盘两个 watcher 各装一个 native filter，Qt 又把同一条消息投递两次，于是每条鼠标消息触发 4 次 Python 回调，每次做 2 次 `GetRawInputData` + 分配缓冲 + ctypes 解析。1000 Hz 鼠标下约每秒 4000 次回调，**恰好在玩家操作时最重**。 | 合并为一个 filter；先只读 header（`RID_HEADER`）判断类型，鼠标事件才读全量；同一条消息按 `(time,lParam)` 去重；缓冲预分配。状态本就幂等，不会丢按键边沿。 | A |
| 1.2 | `ui.py:1183-1185, 2242` | 主循环 `tick()` 20 ms（省电 40 ms）常驻：轮询 `GetAsyncKeyState`、`GetForegroundWindow`、`shortcut_keys()`、`visibility_watch()` 等。无地图、游戏不在前台时也 50 Hz 唤醒。 | 空闲（`state.opened` 为假且小游戏未运行）时放宽到 60–80 ms；Raw Input 边沿已缓存在 `pending_edges`，不会丢键，只是快捷键响应延迟最多多几十毫秒。开图期间保持 20 ms。 | B |
| 1.3 | `appearance/player.py:49-65, 106-118` | 布偶定时器**永不停止**：idle 50 ms（20 fps）、matching 33 ms。idle 确有呼吸动作，所以不能静止。每帧 `paint()` 重画全身：两条手臂各约 54 条 2 px 条带 `drawPixmap` + Python 三角函数循环，腿部 `curved_limb` 每帧 numpy 插值；半透明分层窗口每帧整面 `UpdateLayeredWindow` 上传。 | idle 周期 3 s 固定、无随机，可**预渲染一圈帧**（如 30 帧 QPixmap，约 1.5 MB）后按进度取帧 blit；matching/事件动作照旧实时画。或仅把 idle 降到 12 fps。 | B（帧缓存视觉等价，仅时间量化到 1/30 周期） |
| 1.4 | `keyboard_input.py:28-40` + `src/ui_trace.py` | `report()` 每 5 s 写一次 `input-health.jsonl`（mkdir+open），空闲也写。 | 只在计数变化时写。 | A |
| 1.5 | `theme.py:9-42 chalk_texture` | `lru_cache(48)` 以精确像素尺寸为 key；滑块 `filled.width()` 每个值一个条目，折叠栏/滚动条用整窗尺寸，容易把缓存冲掉后反复用 numpy 生成 2× 纹理（几十 ms、几十 MB 临时数组）。只在面板打开时发生。 | 缓存容量提到 256；滑块已填充部分改为整条纹理裁剪绘制。 | A |

### 2. 打开地图期间

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| 2.1 | `window_map_capture.py:57-115`；调用点 `ui.py:2197-2240` | 可见性守卫每 0.8 s（省电 1.6 s）**新建一个 Windows.Graphics.Capture 会话**（D3D 设备、frame pool、独立线程），拿一帧就 stop，再起一个线程以 20 ms 轮询最长 3 s 等原生线程退出。每秒约 1.25 次会话创建/销毁 + 两个辅助线程。 | 同一 hwnd 保持一个长驻会话（`game_scene_watch.py:68` 已有 `minimum_update_interval` 用法），按需取最新帧；保留现有超时/slot 保护。 | B（会话生命周期改变，截到的帧内容相同；文件注释提到驱动 stop 不稳定，要保留兜底） |
| 2.2 | `window_map_capture.py:38 normalize_frame`、`src/windows.py:68`、`src/macos.py:107-112` | BGRA→BGR 用 `pixels[:,:,:3].copy()` numpy 跨步拷贝（1440p 约 11 MB），GDI 路径再多一次 `GetBitmapBits` 拷贝，mac 路径 `bytes()` 再拷一次。 | 改 `cv2.cvtColor(..., COLOR_BGRA2BGR)`，去掉多余拷贝。像素值一致。 | A |
| 2.3 | `src/macos.py:87-116`、`macos_capture.py:51` | 每次截图都重新 `SCShareableContent` 枚举全部窗口（50–200 ms），并且每帧写两条 trace 到磁盘。 | 按 `(window_id,pid)` 缓存 filter/config，失败时再枚举；trace 只在首次/失败时写。 | A |
| 2.4 | `ui.py:1905-1912` | 开图探测最多 6 次 `inspect_map_ui` 在 UI 线程（每次约 20–40 ms）。 | 保持；量小。可选挪到线程。 | — |
| 2.5 | `src/live.py worker` / `src/matcher.py` | 匹配子进程：`match()` 最多 3 轮 `_match_view`，每轮 extract + 全库 knnMatch + top10 Powell。噩梦多人再叠 SharedTerrain/MultiplayerFallback。已 `cv2.setNumThreads(1)`。 | **不动**。它是开图瞬间的突发，不是常驻发热；并行化反而增加发热。 | — |

### 3. 小游戏运行期间（桌面宿主）

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| 3.1 | `minigames_ui.py:117-119, 298-305` | `window_timer` 每 200 ms 读并 JSON 解析 `window-state.json`。 | 先比 mtime，变化才解析。 | A |
| 3.2 | `scripts/game_launcher/windows.cs:99-111, 207-214`（macOS `macos.swift` 同理） | 启动器每 100 ms 轮询命令文件；每 1 s 在 WebView2 执行 JS 读 localStorage 并**无条件写** `audio.json`。 | 内容变化才写；命令通道改 `FileSystemWatcher`。 | A |
| 3.3 | `minigames_ui.py:245-248` | 每个 20 ms tick 调 `shortcut_keys()`（函数内 import + set 推导）。 | 偏好变更时才重算并缓存。 | A |
| 3.4 | `game_scene_watch.py` | WGC 长驻会话 1.5 s 一帧 + 小图统计，CPU 侧几毫秒。设计合理。 | 可选：游戏不在前台时暂停会话。 | B |
| 3.5 | 小游戏网页本身 | 见第三节（待网页端审计结果补充）。 | | |

---

## 二、Android 端

### 1. 待机（识别睡眠，只有 1 s 一次的低分辨率探测）

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| A1 | `CaptureService.java:386-432`、`IdleMapProbe.java:28-50`、`mobile_gate.py` | 每 1 s（省电 2 s）：VirtualDisplay 缩到 480 宽取一帧 → `Bitmap.createBitmap` → **PNG 编码**（Java）→ Python `cv2.imdecode` → `inspect_map_ui` 再把 480 宽**放大到 1280** 做 3 模板 × 8 尺度的 `matchTemplate`。 | ① 去掉 PNG 往返：Java 把 RGBA 原始字节直传 Python，`np.frombuffer` 直接成图（PNG 无损，像素完全一致）。② 模板各尺度 `cv2.resize` 结果用 `lru_cache` 缓存（每次省 24 次 resize）。③ 480×h Bitmap 与 ByteBuffer 复用（`RgbaRows.java:11` 每次整帧分配）。 | A |
| A2 | `GameBadgeView.java:30` | 悬浮球 `onDraw` 末尾无条件 `postInvalidateDelayed(200)`：只要悬浮球在，**5 Hz 永久重绘**，且每帧调 `GameIcons.bitmap()` 做 3 次文件 stat。 | 去掉自调度，改为 `MiniGameOverlayService.hideGame/showGame` 和 `activeGameId` 变化时 `invalidate()`；图标按 id 缓存引用。 | A |

### 2. 开图 / 识别期间

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| B1 | `CaptureService.java:1097-1128 encode/encodeFloorHeader`、`mobile_bridge.py decode/match`、`runMatch:1565-1587` | 每次 gate 心跳（800 ms，画面有变化时）和每次匹配：`createScaledBitmap` 到 1440 宽 + **PNG 压缩**（手机上 50–150 ms）→ Python `imdecode`（20–40 ms）；楼层头部再一次 PNG；匹配结果全屏 BGRA 层 `cv2.imencode('.png')` 写文件 → `BitmapFactory.decodeFile`。估算开图期间 PNG 编解码占用约 20–30% 单核。 | 三处都换成原始像素直传：帧用 RGBA 字节 + 宽高（Chaquopy `byte[]`→`bytes`，零编码）；结果层用 numpy 缓冲 → `Bitmap.copyPixelsFromBuffer`。PNG 是无损格式，换掉后送入门控与匹配的像素**逐字节相同**。 | A |
| B2 | `CaptureService.java:1719-1747 grab()` | 每次全屏 grab 分配 padded 全屏 Bitmap + crop 副本 + `cleanCaptureFrame` 副本（各约 10 MB），每 800 ms 一次 → GC 压力与内存带宽。 | 复用 Bitmap；`cleanCaptureFrame` 用 `copy` 改为复用目标。 | A |
| B3 | `CaptureService.java:249-258, 435-439` | 主 VirtualDisplay **以屏幕原生分辨率**（如 2400×1080）镜像，识别醒着时 SurfaceFlinger 每帧（60–120 fps）合成一份全屏副本，约 10 MB/帧带宽。而所有消费者里，`encode()` 本来就缩到 1440 宽，`inspect`/`inspect_floor_tabs` 内部都再缩到 1280 宽，160×90 采样与分辨率无关；只有 `read_floor_header` 文档上说用原生分辨率，但它内部仍经 `inspect_floor_tabs` 缩到 1280。 | 把 VirtualDisplay 建成 1440 宽（保持比例），省掉 `createScaledBitmap` 和约 2.8× 的合成/带宽。需要同步 `grab()` 的尺寸假设和叠图层尺寸换算（叠图 ImageView 是 FIT_XY，层按截图尺寸生成即可）。 | C（缩放由 SurfaceFlinger 完成而非 `createScaledBitmap` 双线性，像素略有差异；门控/楼层数字读取需真机回归） |
| B4 | `mobile_matching.py selected_floor`、`manual_alignment.py manual_floor_reading`、`read_floor_header` | 每次匹配楼层读取最多跑 5 次 `inspect_floor_tabs`（原图 + 2 档增益 + 2 种插值），每次先对**整张全尺寸零画布**灰度+缩放。 | `read_floor_header` 只构造 1280 宽画布；5 次调用共享一次灰度/缩放。数值等价（缩放因子相同）。 | A/B（需核对 `factor` 路径完全一致） |
| B5 | `CaptureService.java:615-621 overlay` | 叠图是全屏 `TRANSLUCENT` 窗口 alpha 0.3，GPU 每帧混合整屏。 | 按层的非透明包围盒裁小窗口（桌面端 `Overlay.update_manual_mask` 已有同类做法）。 | B |

### 3. 小游戏期间（手机）

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| C1 | `MiniGameOverlayService.java:198-206 requestHighRefreshRate` | 小游戏窗口把 `preferredRefreshRate` 设为面板**最高模式**（120/144 Hz），并 `web.setRequestedFrameRate(rate)`；只有省电模式才压到 60。整屏和 WebView 的 rAF 都跑高刷，GPU/CPU 接近翻倍。**这是手机小游戏发热最直接的来源。** | 默认 60，高刷改为显式选项。 | B（顺滑度略降） |
| C2 | `CaptureService.java:434 recognitionIdle()`、`:282-313 watchMiniGameScene` | 小游戏运行时 `recognitionIdle()` 为假 → **全分辨率 VirtualDisplay 整个小游戏期间常开**，只为每 1.5 s 采 160×90 个点做场景变化检测。 | 场景检测改走 `IdleMapProbe` 式的 480 宽脉冲（每 1.5 s 短暂挂 surface），其余时间 surface 为 null。 | C（采样来源从全分辨率点采样变为缩放后帧，`GameSceneDetector` 阈值需真机复核；可先对照 `android/tests/GameSceneDetectorTest.java` 的回放数据） |
| C3 | `MiniGameOverlayService.java:213-223 sceneOverlaySignature` | 每 1.5 s 在主线程 `Bitmap.createBitmap(160,90)` + `shell.draw(canvas)`（对 WebView 软件光栅化整页）+ `new int[14400]`。 | 复用 Bitmap/Canvas/int[]；进一步可用 `PixelCopy` 异步读回。 | A（复用）/ B（PixelCopy） |
| C4 | `MiniGameOverlayService.java:171-178 hideGame` | 隐藏只 `removeViewImmediate` + 静音，从不调 `web.onPause()/pauseTimers()`；手动最小化后 JS 定时器、Web Audio 无限期后台跑。 | `hideGame` 调 `web.onPause()`，`showGame` 与保存前 `onResume()`。 | B（需验证隐藏态保存流程 `__jellyfishHostSave` 仍能完成） |
| C5 | `SharedScreenRecorder.java:227-254` | 录屏音频泵 `postDelayed(this,10)`，每秒 100 次 Looper 唤醒。 | 改 20 ms 并每次多读，时间戳按累计帧数算。 | A |
| C6 | `Theme.java:277-280, 533-551` | `ChalkDrawable.draw` 在 opacity<1 时 `saveLayerAlpha` 离屏层（所有标题/按钮）；`ChalkSlider` 按填充像素宽生成纹理，拖动时每个 move 事件重生成并挤掉 LruCache。只在设置页。 | 用 paint alpha 直接 `drawBitmap`；滑块填充用整条纹理裁剪。 | A / B |

---

## 三、小游戏网页端与运行时

归属先说清楚：`minigames/*/game/**` 是按 sha256 下载安装的上游包（`.gitignore` 忽略、`scripts/build_native_games.py:79-95` 逐字节校验），**不能直接改**；能在本仓库改的是 `games/jellyfish/fixes/`（已随包发布的补丁）、`scripts/game_launcher/*`（桌面启动器）和 Android 的宿主脚本 `android/app/src/main/assets/*.js`。

### 1. 合成大水母（最热，标题页不玩也满负荷）

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| J1 | 上游 `jellyfish-animation.js:85-117` | 3 级以上每条水母每帧走 WebGL：`canvas.width=item.w` 按尺寸交替变化触发 drawing buffer 重分配，`preserveDrawingBuffer:true` + 每条一次 `ctx.drawImage(glCanvas)` GPU→2D 回读。标题页同样每帧画 11 条。 | **Android 宿主已经有现成解法**：`android/app/src/main/assets/host-animation-cache.js` 把每级呼吸动画缓存成 24/48 帧离屏 canvas，只注入手机。桌面启动器 `windows.cs`/`macos.swift` 没有注入。把同一脚本注入桌面 WebView2/WKWebView 即可，不碰上游。 | B（手机上已验证的观感；帧相位量化到 1/48 周期） |
| J2 | `games/jellyfish/fixes/native-physics.js:52` + 上游 `config.js:31` | `world.step(delta,16,16)`（planck 默认 8/3）× 120 Hz 固定步长，每秒最多 120 次 16/16 迭代求解；`sync()` 每步为每个 body 新建快照对象并遍历整个 contact 列表。 | 迭代降到 10/6 或 8/3，保持 120 Hz；需复跑上游 `tests/physics.cjs` 的 60 体静止测试（见 `native-circle-physics.patch`）。 | C（可能轻微改变堆叠手感，需你决定） |
| J3 | 上游 `game.js:1446-1447, 910-914, 1000-1013` | 画布固定 2559×1441 后备缓冲不随窗口缩放；每帧 `getBoundingClientRect`+写 style 强制 layout；每帧全屏画 14 MB 背景。 | 只能走上游仓库或补丁；本仓库不动。 | — |
| J4 | `game.js:784` | 只在 `document.hidden` 时存档，循环不暂停；桌面「隐藏」= 最小化，Chromium 会节流 rAF，基本没问题。 | 见运行时 R1 的 `TrySuspendAsync`。 | — |

### 2. 邦邦小厨房（第二热）与蚀骨赠礼（最轻）
- 厨房：上游 `cooking-fx.js:80-108` 每个燃着的锅每帧 128 次带 alpha 的 `drawImage`，画布接近 10 Mpx；`ctx.filter`/`shadowBlur` 走软件路径。全是上游代码，本仓库无法改。
- 扫雷：无主循环，`setInterval 200ms` 且 `visibilitychange` 正确暂停；持续开销只有 CSS 蒸汽 `blur` 动画与 3840×2160 背景。上游代码，影响小。

### 3. 桌面运行时（我们的代码）

| # | 位置 | 现状 | 方案 | 风险 |
|---|---|---|---|---|
| R1 | `scripts/game_launcher/windows.cs:99-111, 207-214`；`macos.swift:101-103` | 100 ms 轮询命令文件；每 1 s `ExecuteScriptAsync` 读 localStorage 并无条件写 `audio.json`；最小化时也跑。 | 命令改 `FileSystemWatcher`；音量只在变化时写；最小化时 `CoreWebView2.TrySuspendAsync()` 彻底挂起渲染进程，恢复时 `Resume()`。 | A（前两项）/ B（挂起：恢复瞬间可能有 100–300 ms 空白） |
| R2 | `windows.cs` 注入点 | 桌面没有注入 `host-animation-cache.js`（见 J1）。 | 与 Android 一样在加载时注入。 | B |

另：`docs/minigames.md` 全文中文已损坏为 `?` 字节（`od -c` 证实），与性能无关，但需要从历史记录恢复。

---

## 四、建议的实施顺序

**第一批：零行为变化（A 级），改完跑现有测试即可**
1. Android：PNG 往返全部换原始像素直传（A1①、B1）——开图期间最大的单项 CPU。
2. Android：悬浮球 5 Hz 自刷新去掉（A2）；模板缩放缓存（A1②）；Bitmap/缓冲复用（A1③、B2、C3）；音频泵 20 ms（C5）。
3. 桌面：Raw Input 合并 filter + 一次读取 + 去重（1.1）——玩游戏时直接受益。
4. 桌面：截图路径 `cvtColor` 替代切片拷贝（2.2）；mac 缓存 ShareableContent、少写 trace（2.3）；启动器/状态文件只在变化时写（3.1、3.2）；`chalk_texture` 缓存容量（1.5）。

**第二批：观感/时序微调（B 级），需要你确认接受**
5. 手机小游戏默认 60 Hz（C1）——手机小游戏发热最大项。
6. 桌面启动器注入 `host-animation-cache.js`（J1/R2）——桌面水母发热最大项，手机已验证。
7. 隐藏小游戏时 `WebView.onPause()`（C4）；桌面最小化时 `TrySuspendAsync`（R1）。
8. 桌面布偶 idle 帧缓存（1.3）；空闲 tick 放宽（1.2）。
9. 桌面开图期间长驻 WGC 会话（2.1）。

**第三批：影响判定或手感（C 级），需要真机/实测回归，建议单独做**
10. VirtualDisplay 降到 1440 宽（B3）。
11. 小游戏期间场景检测改低分辨率脉冲（C2）。
12. 水母物理迭代 16/16 → 10/6（J2）。

**明确不动的部分**：匹配核心（`evidence/retrieval/registration`）、门控阈值、楼层判定逻辑、所有 `live.py` 的接受条件。

## 五、实施记录（2026-11-06，第一、二批）

已改动的位置与验证方式；第三批（B3、C2、J2）未动。

**Android**
- `mobile_bridge.py`：新增 `decode_raw`，`decode/inspect/read_floor_header/match` 增加 `width/height/stride` 参数（0 时仍走 PNG，旧契约不变）；`match(..., layer_format='raw')` 时把叠图层按 `Bitmap.copyPixelsFromBuffer` 的预乘 RGBA 写出并返回 `layer_width/height`。`mobile_gate.py` 与桌面 `map_visibility.py` 缓存各尺度模板。离线验证：同一帧 PNG 路径与原始路径解码像素逐字节相同、`inspect` 结果相同（电脑上 84 ms → 47 ms）。
- `CaptureService.java`：`RawFrame` 取代 PNG 字节（门控心跳、楼层头部、匹配输入、叠图输出四处）；诊断开关下才临时压一张 PNG；`grab()` 改为一次打包拷贝；`refreshBadge()`。
- `GameBadgeView.java`：去掉 200 ms 自刷新。`MiniGameOverlayService.java`：隐藏时 `WebView.onPause()`、显示/保存前 `onResume()`；默认 60 Hz，`game_high_refresh` 偏好开启才拉高刷；场景签名缓冲复用。`MainActivity.java`：辅助设置新增「小游戏高刷新率」开关。`SharedScreenRecorder.java`：音频泵 20 ms。`Theme.java`：`ChalkDrawable` 用画笔透明度代替离屏层，滑块填充改为整条纹理裁剪。
- 验证：`assembleDebug` 编译通过；Python 侧契约测试（manual_alignment / latest_request / background_memory / mobile_matching_policy / image_decoding / recognition_liveness）通过。**未在真机运行**：叠图显示、隐藏小游戏后恢复与保存、60 Hz 观感都需要实机确认。

**桌面**
- `mouse_input.py` / `keyboard_input.py`：新增 `RawInputFilter`，全进程一个 filter，只在 `windows_generic_MSG` 那次读、一次 `GetRawInputData` 进预分配缓冲、按类型分发；`report()` 只在计数变化时写日志。
- `ui.py`：空闲时 tick 60 ms（省电 80 ms），有地图/采集/匹配/小游戏时仍 20 ms；新增 `window_watch()`，开图期间可见性守卫复用一个长驻 `WindowWatch` 会话，`close_map/shutdown` 释放。`window_map_capture.py`：新增 `WindowWatch`，会话槽 2 → 3；`normalize_frame` 用 `cvtColor`。`src/windows.py`、`src/macos_capture.py` 同样去掉一次整帧拷贝；`src/macos.py` 两条每帧 trace 改为变化时才写。
- `appearance/player.py`：idle 呼吸循环预渲染 30 帧缓存（按尺寸与 DPI 分组），只在帧序号变化时重绘。
- `minigames_ui.py`：`window-state.json` 按 mtime 变化才解析；`shortcut_keys()` 按偏好签名缓存。`theme.py`：`chalk_texture` 缓存 48 → 256。
- 本机端到端实跑（进程内启动助手，用无边框窗口「第五人格」显示 `examples/0/example.png`，调用 `open_map` 走真实 WGC 截图 → 子进程匹配 → 叠图 → 可见性守卫 → `close_map`）：叠图 1.1 s 出现（匹配 692 ms），长驻会话在 6 s 守卫期内一直持有有效帧、叠图不被误撤、`close_map` 后会话槽全部释放；空闲时进程 CPU 约 1%（布偶开启、帧缓存 30 帧），注入约 600 次/秒鼠标移动时约 7%。实跑中发现并修正：WGC 只在窗口内容变化时发帧，静止窗口不会有「新鲜」帧，`WindowWatch.latest` 改为只以 10 s 作为会话失活上限，不再要求帧新鲜；超过上限才回退到单次截图并重建会话。
- 验证：`mapmatching/tests` 283 项，除 3 个文件原本就失败（`test_failure_session`、`test_closed_map_fallback`、`test_no_map_signal`，失败点都在本次未改的、工作区里尚未提交的代码或缺失的样例图上）外全部通过。**未实机运行**：长驻采集会话在真实驱动上的稳定性、Raw Input 只读 generic 一次在各类游戏（含管理员权限游戏）下的快捷键响应，需要你在 Windows 上实际开图/按键确认。macOS 改动无法在本机验证。

**桌面启动器（`scripts/game_launcher`）**
- `windows.cs`：命令文件改 `FileSystemWatcher`（保留 2 s 慢速兜底；auto-hide 的 5 s 自动关闭另用一次性计时器，时序不变）；`audio.json` 只在内容变化时写，最小化时不再每秒跨进程执行脚本；最小化 500 ms 后 `TrySuspendAsync()` 挂起 WebView2（页面未加载完时先等加载），恢复/保存/关闭前先 `Resume()`；与 `safe-exit.js` 同机制注入 `host-animation-cache.js`（从 Android 逐字节复制到 `scripts/game_launcher/`）。`macos.swift`：同样注入缓存脚本、音量只在变化时写；未做挂起与监视（Swift 本机无法编译，只做了逐行检查）。`build_native_games.py` / `build_local_game_launcher.py` 复制新脚本进 runtime。
- 验证：csc 编译通过（输出在临时目录，未写入 `minigames/runtime`）；`scripts/test_game_host_bridge.py` 通过；用临时编译的启动器实跑合成大水母：探针确认 `JellyfishAnimation.draw` 已被缓存版替换，hide/show 三轮挂起/恢复正常，auto-close 5.4 s，`show` 命令 55 ms 送达，`audio.json` 不再每秒重写。**正式 runtime 里的 GameLauncher.exe 需要重新走 `build_native_games.py` 发布流程才会带上这些改动。**

## 六、现场说明
- 工作区当前有 124 个已修改文件未提交（0.6.11 之后的改动）。任何优化都会叠在这些未提交改动之上，建议先把现状提交一个快照再开工。
- 第一批里 Android 的改动需要重新 `prepare_android.py` + 构建 APK 真机验证；桌面改动可用 `python -m unittest discover -s mapmatching/tests` 回归。
