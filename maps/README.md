# 地图库：地图 → 作者 → 难度

默认使用凉哈皮。设置中的“地图版本”可切换为展十，展十提供噩梦全棺和速刷两种参考路线。

## 目录层级（2026-11-06 起）

```
maps/
├─ curse/                    厄运之女
│  ├─ lianghapi/{normal,hard,nightmare/{solo,duo}}/
│  └─ zhanshi/{normal,hard,nightmare}/{full,speed}/
├─ linguang/                 磷光症
│  ├─ lianghapi/{normal,hard,nightmare/{solo,duo}}/
│  └─ zhanshi/{normal,hard,nightmare}/{full,speed}/
├─ _unindexed/  _overview/   同前
├─ recognition-inputs/  evidence/  index.json   派生物与底稿，不分层
└─ floors.json  disabled.json  providers.json
```

每个作者在每张地图下的全部难度槽位都已建好（空目录放 `.gitkeep`），作者补图时直接放进对应
目录再登记即可。目前已有：厄运之女（凉哈皮困难/噩梦，展十困难/噩梦）、磷光症（凉哈皮困难 13 张、噩梦 15 张，
展十困难十六棺 12 张、噩梦十四棺 15 张）。`datasets/tools/restructure_maps.py` 负责把旧的 `maps/<作者>/...` 搬到
这个层级；厄运之女的 `map_id` 不变（它是身份不是路径），磷光症的 `map_id` 就是
`linguang/<作者>/<难度>[/<路线>]/<名字>`。界面「录入新地图」也按这个层级存放。

## 第二张游戏地图：磷光症（2026-11-06）

设置里新增「地图」选择：厄运之女（默认，原有全部图库）/ 磷光症。登记条目用 `scene` 字段区分
（缺省即 `curse`=厄运之女），`mapstore.load_references` 按 scene 过滤，两张游戏地图的图**永远不会**
进同一个候选池。磷光症的难度跟随作者：凉哈皮最初只有困难（14 张，其中地图9 与地图8 同地形已停用，`linguang/lianghapi/hard/<入口>/地图N`，
三层纵向排列，由 `datasets/tools/import_linguang_lianghapi.py` 按空行切分，标题缩略图和图例进 `exclude_regions`），
展十有噩梦「十四棺图」（15 张，`linguang/zhanshi/nightmare/full/N`，负一层左上、负二层右上、负三层下方，
由 `datasets/tools/import_linguang.py` 按固定版式分区）和困难「十六棺图」（12 张，`linguang/zhanshi/hard/full/N`，
2026-11-08 由 `datasets/tools/import_linguang_zhanshi_hard.py` 导入，版式相同，作者按负一层/负二层形状命名的目录与文件名
保留在条目 `name` 里；同目录下两张教学图按尺寸跳过）。版式不符的图会被拒绝而不是猜；
选区预览分别在 `datasets/evaluation/linguang-lianghapi-import/`、`linguang-import/` 和 `linguang-zhanshi-hard-import/`。
磷光症全部 56 张图（含已移除的地图9）都走和手动录入一样的存储策略 `webp-2048-q90-v1`（最长边 2048、WebP 质量 90），
显示图合计约 5.6 MB；识别特征另存，不进发布包的显示图体积。
`mapmatching/src/context.py` 的 `SCENE_CONTEXTS` 记录每位作者已有的难度，作者补图后在那里放开。

磷光症的楼层按钮是右侧竖排的 −1/−2/−3/−4，与厄运之女横排的 1/2/−1 不同，由 `floor_tabs.inspect_basement_tabs`
单独读取（2026-11-07）：找出唯一一个高亮方块，再沿同一列找齐四行带减号的暗标签，按高亮所在的行号得出楼层；
列不完整（缩放把细的「1」抹掉）、高亮里没有标签、两处高亮时一律返回未知而不是猜。`live.tab_reader` 按图库楼层
选读取器（有 1/2 层用横排读取器，全是地下层用竖排读取器），两种读取器互不认对方的按钮。读到的楼层只作候选提示和
跨层「直接叠图」的依据；读到图库没有的负四层时直接提示「负4层没有参考图」，不再去其它楼层硬搜，也不弹直接叠图。
这列按钮落在手机地图视口之内（厄运之女的横排在视口上方），高亮方块本身就是一块低饱和亮斑，空楼层时足以凑出一个假配准，
所以读到列之后桌面与桥接都用 `hide_floor_column` 把它抹黑再提特征；桌面端的手动跨层（`cross_floor_candidate`）也改为
先按 `phone_viewport` 裁到视口，与正常识别看同一块像素，右缘的导航/缩放/定位图标不再冒充地图结构。
双端跨层流程（查看 −3 弹「直接叠图」、强制后居中或配准、查看 −4 拒绝）有回归 `tests/test_basement_tabs.py::CrossFloorTests`。
PC 客户端（16:9，右上角是 ESC 提示而不是关闭叉）同样能读：亮度步长封顶、暗标签门槛放低、只认落在按钮格点上的行，
顶部的昵称/水印文字不会被当成一行；桌面端「地图已展开」门槛补了「全览图标 + 竖排楼层列」这条兜底，PC 端没有关闭叉也能过。
PC 样本是 B 站视频截帧裁下的按钮列（`tests/fixtures/linguang-tabs/pc-viewing-2.png`），回归 `PcClientTests`。
安卓面板同样有「地图」选择，桥接 `mobile_bridge.initialize` 按 `scene` 加载，`CaptureService` 的楼层表头裁到半屏高
以覆盖竖排按钮，桥接按 `scene` 选读取器。回归用的按钮列裁片在 `mapmatching/tests/fixtures/linguang-tabs/`，
三张原始手机截图和叠图复盘在 `datasets/evaluation/20261107-linguang-phone/`。

两位作者的磷光症图**不是同一批版型**：展十的 15 张噩梦十四棺图与凉哈皮的 14 张困难图两两交叉比对（`datasets/evaluation/
20261107-linguang-phone/cross-author-floor-table.json`）没有任何一层能对上，所以噩梦十四棺只有展十有图，困难则凉哈皮和展十各有一套（展十困难十六棺 2026-11-08 加入），
选错作者或难度只会得到「地图对齐证据不足」。`SCENE_CONTEXTS` 里展十现在是 `('hard','nightmare')`，桌面和安卓的难度
选择在「磷光症 · 展十」下放开为困难/噩梦。

**凉哈皮磷光症噩梦（2026-11-13）**：15 张，`linguang/lianghapi/nightmare/<入口>/地图N`（`mode` 为空，凉哈皮的磷光症噩梦只有一套，
不分单人/多人），版式与凉哈皮困难相同（1000×3500，三层纵向），由 `datasets/tools/import_linguang_lianghapi_nightmare.py`
复用困难的切层逻辑导入，原图在仓库根目录 `凉哈皮加页手记《磷光症》噩梦难度路线图/`（作者同时给的「一图流」总览 PNG 不是
图集，跳过）；选区预览在 `datasets/evaluation/linguang-lianghapi-nightmare-import/`。这套与展十噩梦十四棺**是同一批 15 张地图**：
朋友的 36 张 PC 帧与三张手机截图在两套图库里两两一一对应、楼层一致（展十 1/2/3/4/5/9/11/13/14 ↔ 凉哈皮 地图3/8/5/13/6/14/1/12/10），
所以噩梦局选哪位作者都能识别。`SCENE_CONTEXTS` 里凉哈皮放开为 `('hard','nightmare')`，双端「磷光症 · 凉哈皮」都可选困难/噩梦。
展十困难与凉哈皮困难交叉比对（`datasets/evaluation/20261107-linguang-phone/cross-author-floor-table-hard.json`）证明两套困难图
是同一批版型：展十 1–7、9、11、12 分别对应凉哈皮 地图14、11、6、5、12、8、2、4、3、7，展十 8、10 和凉哈皮 地图1、地图13 各自只有一方画了。凉哈皮的 `左直线/地图9` 与 `地图8` 地形和路线逐像素相同（只有标题缩略图不同），
两条同地形条目会让识别永远判为「两张地图过于相似」，已在 2026-11-07 用 `set_map_enabled` 移入 `disabled.json`
（本机），发布包只打 `floors.json` 里的条目，客户端更新作者图库后旧条目会被清掉。
两位作者的发布包（`IdentityVMapAssistant-Maps-<作者>.zip`，由 `scripts/build_matching_module.py` 打包）
包含该作者在两张游戏地图下的全部图，客户端更新作者图库即可得到磷光症；安装会按 `map_id` 替换旧条目并删掉旧路径文件。

```
maps/
├─ lianghapi/hard/                 凉哈皮困难原图
├─ lianghapi/nightmare/solo/        凉哈皮单人路线
├─ lianghapi/nightmare/duo/         凉哈皮多人路线
├─ zhanshi/full/                   展十全棺原图（保留原分类和文件名）
├─ zhanshi/speed/                  展十速刷原图
├─ providers.json                  作者与路线目录，默认 lianghapi
├─ floors.json                     地图登记、原图校验、楼层选区
├─ evidence/                       可重建的识别特征
└─ index.json                      可重建的特征索引
```

大图录入后按最长边 2048 像素、WebP 质量 90 压缩，不放大、不拉伸；小于 256 KiB 且未超尺寸的图片原样保留。楼层选框和多边形同步换算。旧版 maps/hard、maps/nightmare 路径仍可读取，用户已有地图不要求迁移。
没有 provider 字段的旧条目归属凉哈皮，旧 map_id 保持不变，人工标注答案不变。
展十原始 zhanshi 文件夹保留不动，三张说明图片不参与识别。

展十图按实际地形划分一楼、二楼、地下室，并用多边形隔开相邻楼层。识别特征排除高饱和路线、星标和灰色水印；显示使用压缩后的彩色图。
先用公共地形库确定地图身份，再在所选作者原图上独立计算缩放和位置；切换作者会清空当前识别记忆。
两套图的对应关系来自完整三层轮廓比对，不读取实机数据集的人工作答。

数据整理脚本、选区预览、对应关系和测评结果统一在 datasets/：
- datasets/tools/import_zhanshi.py：复制展十原图、生成分区和索引、链接共同地形。
- datasets/tools/link_zhanshi.py：用三层完整轮廓生成对应关系；分差不足时停止，不自动猜测。
- datasets/evaluation/zhanshi-integration/floor-regions.jpg：逐图选区总览（绿=一楼、黄=二楼、蓝=地下室）。

以下是旧版登记与管理规则，路径示例适用于旧库；新录入按作者子目录保存。

# maps/ — 地图库

所有和地图有关的东西都在这里，只有这一处。内置原图和手动录入的图**没有区别**：
躺在同一棵树里、进同一张登记表、走同一套增删。

```
maps/
├─ hard/                        困难原图
├─ nightmare/solo/              噩梦·单人原图
├─ nightmare/duo/               噩梦·多人原图
├─ _unindexed/                  放进来但**没有登记**的图，不参与匹配
├─ _overview/                   一图流总览大图，人工查阅用；从不进索引
├─ floors.json                  登记表 —— 唯一手工维护的文件
├─ disabled.json                被移除的条目，原样存放，恢复就是搬回去
├─ index.json                   索引缓存（派生物，可重建）
└─ evidence/<16位十六进制>.npz   每张图的特征（派生物，可重建）
```

## 唯一需要记住的规则

> **文件在 `maps/<难度>/[<人数>/]` 下，且 `floors.json` 里有一条同名条目 = 参与匹配。**
> **只有文件、没有条目 = 只是躺着。**

粘贴文件进这个目录**不会**让它被识别，这只是「把素材放进来了」。要让它参与匹配，
走界面上的「管理地图 → 新增地图」，或者直接编辑 `floors.json` 后重建索引。
要让它停下来，走「移除」（软删除，原图和特征都留在盘上，随时能恢复）。

`_` 开头的两个目录是**例外区**，永远不会被索引：

- `_unindexed/`：图已经在库里，但 `floors.json` 里没有条目。往里放不算登记。
- `_overview/`：一图流总览大图（三张，共 137 MB）。它们是给玩家看的合成大图，
  不是单张门图，**从来没有进过特征索引**，也不该被录入。放在这里只是为了让
  「所有地图相关的图都在 `maps/` 下」这句话成立；打包时会被排除。

## 文件名就是身份

`map_id = <难度>[/<人数>]/<文件名去掉后缀>`。改文件名等于换了一张图，
`floors.json` 里的键会对不上。文件压缩不改变 map_id。`sha256` 校验压缩后的文件；`storage.original_sha256` 保留用户提供的原文件哈希，供评测配对和重复录入检查使用。

## 派生物

`index.json` 和 `evidence/` 都是**派生**出来的，删掉不会丢信息，跑一次重建就回来：

```powershell
python -m mapmatching build-index
```

重建是增量的：`sha256` 和 `entry_sha` 都没变的条目直接复用旧特征，只抽新图或改过楼层框的那几张。
只改了楼层框（没换图）时不需要重新录入，重建索引就够了 —— 管理列表里那一行会显示「需重建索引」。

`floors.json` 是**活的用户数据**（录入、移除都会改它），所以索引的过期判定是**逐图**的
（每条记一个 `entry_sha`），不是整份文件的哈希 —— 否则录入一张图就会让整个索引作废、
逼一次全量重建。细节见 `mapmatching/src/mapstore.py` 的模块注释。

## 图片压缩与识图底稿

- 地图显示图片：最长边 2048 像素，WebP quality=90，保持长宽比。
- 识图底稿：`recognition-inputs/` 中的无损 PNG，仅保存原图在算法工作分辨率下的地形掩码，全部 188 张共约 0.94 MiB。它不是可删除缓存；下载包、更新和删除地图都包含它。
- 识图特征从底稿重建，不从有损显示图重建，避免文字、边缘的压缩误差改变匹配结果。老地图没有底稿字段时继续兼容原来的图片提取流程。
- `storage.original_size` 和 `storage.resize` 记录原始尺寸与坐标转换。已有人工标注不修改；审阅工具和评测入口按坐标框架换算，新标注记录 `reference_size`。
- 新录入的大图在存入地图库时自动压缩，用户选择的原始文件不覆盖。已有本地个人地图不自动改写。
- 发布前的完整地图备份保存在 `datasets/backups/`，不要清理备份来代替正式地图的优化。
