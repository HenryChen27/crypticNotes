"""Render the measured audit plus explicitly marked manual observations."""
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out/mapmatching'
d = json.loads((OUT / 'data_audit.json').read_text(encoding='utf-8'))
refs = [r for r in d['images'] if r['role'] == 'reference']
examples = [r for r in d['images'] if r['role'] == 'example_screenshot_candidate']
pairs = [r for r in d['images'] if r['role'] == 'example_reference']
# Manual rough boxes from contact-sheet inspection, normalized to full screenshot.
# They are audit observations, never production ROI or pose ground truth.
boxes = [(0.35, .29, .55, .54), (.45, .29, .82, .76), (.49, .32, .86, .62), (.39, .40, .60, .59), (.48, .23, .71, .47), (.50, .16, .64, .51)]
annotations = []
for r, box in zip(examples, boxes):
    annotations.append({'path': r['path'], 'source': 'manual contact-sheet inspection', 'visible_structure_bbox_normalized_approx': box, 'bbox_is_not_minimap_viewport': True, 'floor': None, 'floor_note': 'top-right 1/2 selector visible; apparent 1 selection requires full-resolution confirmation before GT', 'fog_mask': None, 'fog_note': 'dark background around visible structure is unknown; cannot distinguish fog from exterior by brightness', 'rotation_degrees': None, 'rotation_note': 'axis-aligned geometry visually compatible with zero rotation, not landmark-validated', 'scale': None, 'scale_uncertainty': None, 'extra_window_occlusion': r['path'].startswith('examples/5/')})
(OUT / 'visual_annotations.json').write_text(json.dumps(annotations, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Data audit — Map Matching v2 / Phase 0', '', '本轮只审计并制定 baseline 计划，按需求末尾指示停在审计阶段。无新匹配结果。', '', '## 1. 扫描范围与来源', '', f"扫描 {d['counts']['files']} 个既有文件，解码 {len(d['images'])} 张图片，解码失败 {len(d['decode_failures'])}。完整路径、字节数、图像尺寸、哈希及色彩统计见 data_audit.json。扫描排除包目录、`maps/evidence`（逐张图的特征派生物）和 .git。未找到 AGENTS.md；未发现 .git 目录。", '',
 # 本节描述的是**当前**的 `maps/` 布局。报告在目录重构后重新生成过，
 # 因此原来的「两个图片文件夹」说法已不适用；第 5 节之后对图像本身的
 # 观察结论没有变 —— 那些图一张都没换。
 '- `maps/hard/`：困难单图。', '- `maps/nightmare/solo/`、`maps/nightmare/duo/`：噩梦单人与双人。', '- `maps/_unindexed/`：放在库里但没有登记（`maps/floors.json` 里没有条目）、因此不参与匹配的图。', '- difficulty 来源是 `maps/` 下的目录层级；solo/duo 来源是子目录名，不是截图推理结果。', f"- {len(refs)} 是单图文件数量，不是已验证唯一拓扑或独立楼层数量。", '', '## 2. examples 与内容核验', '', '| Screenshot | 尺寸 W×H | 同目录配对图（像素哈希与原图库完全一致） |', '|---|---:|---|']
for r in examples:
    pair = next(p for p in pairs if Path(p['path']).parent == Path(r['path']).parent)
    lines.append(f"| {r['path']} | {r['width']}×{r['height']} | {pair['exact_reference_matches'][0]} |")
lines += ['', '以上配对来自用户提供的同目录数据关系，并用 reference 图片像素哈希确认图库身份；没有从 example 编号推断 map。配对本身未用独立 landmark GT 再验证。', '', f"6 张截图均不重复，配对图只有 4 个唯一像素身份：北-T门 2 张、北-1门 2 张、右-双L门 1 张、左-对角门 1 张。Hard 覆盖 4/{len([r for r in refs if r['difficulty']=='hard'])}；Nightmare 截图 0 张。Dataset coverage insufficient。", '', '## 3. 逐张 reference 尺寸 / 格式', '', '| 文件 | difficulty / mode | W×H | 实际编码 |', '|---|---|---:|---|']
for r in refs:
    lines.append(f"| {r['path']} | {r['difficulty']} / {r['mode'] or '-'} | {r['width']}×{r['height']} | {r['format']} |")
lines += ['', '总览属于复合图，不作为 baseline 候选：', '']
for r in d['images']:
    if r['role'] == 'reference_overview':
        lines.append(f"- {r['path']}：{r['width']}×{r['height']}，{r['format']}。")
lines += ['', '## 4. 颜色分布（完整分辨率测量）', '', 'JSON 每张记录 RGB 均值、灰度 [0,10,25,50,75,90,100] 分位数、gray<40、gray>220、HSV saturation>80 比例。这些只是描述统计，不能当作 fog / free-space / wall 分类。', '', '| 类别 | 数量 | dark fraction 范围 | saturated fraction 范围 | 编码 |', '|---|---:|---:|---:|---|']
for role in ['reference', 'reference_overview', 'example_screenshot_candidate']:
    group = [r for r in d['images'] if r['role'] == role]
    # 空组要显式处理：总览图随旧图片目录一起删掉之后，`reference_overview`
    # 这一组就是空的，而 min()/max() 对空序列直接抛 ValueError。
    if not group:
        lines.append(f"| {role} | 0 | — | — | — |")
        continue
    lines.append(f"| {role} | {len(group)} | {min(r['dark_fraction'] for r in group):.4f}–{max(r['dark_fraction'] for r in group):.4f} | {min(r['saturated_fraction'] for r in group):.4f}–{max(r['saturated_fraction'] for r in group):.4f} | {dict(Counter(r['format'] for r in group))} |")
lines += ['', '## 5. 视觉审计：楼层、ROI、HUD、fog、尺度', '', f'- 已检查全部 {len(refs)} 张 reference 联系表和 6 组 example。Hard 图可见 1楼/2楼，部分另有局部插图；Nightmare 图可见 2楼/1楼/地下室，版式与高度不统一。不能按图高中点分层。地下室超出当前 1F/2F 输出范围，后续应显式拒识或扩展 floor schema，不能混入 1F。', '- 地图是带背景纹理的灰蓝填充通道、棕色房间、边界、彩色路线、文字和框线。两域共享部分填充/边界，但 reference 的标注、路线、不同分辨率会污染局部特征；并非纯线稿对纯填充的简单二分。', '- examples/0–4 是带顶部窗口边框和底部任务栏的地图界面截图；地图占游戏主体，不能假定是右上角小地图。截图 5 高度不同，左上和右上有白色窗口遮挡。', '- HUD：左上状态/任务，左下图例，右上楼层选择与关闭/帮助，右侧缩放条，右下全图/定位，底部说明。大致 viewport 是去掉边框后的主体，但 HUD 与主体重叠，单个矩形不足以排除污染。', '- 可见结构近似 bbox 见 visual_annotations.json，坐标归一化到全截图；它们来自人工联系表检查，不是自动 ROI、精确掩膜或 GT。示例 1/2 可见结构较大，0/3/4/5 较小且位置不同。', '- fog/unknown：可见结构外大片暗区；仅靠亮度无法区分未探索区与地图外部。未生成虚假 fog 像素标签，精确 fog 位置和面积为 unknown。', '- 六张截图顶部可见 1/2 控件；不把缩略图上的疑似 1 选中当作已验收楼层 GT。floor accuracy 尚无有效分母。', '- 局部边界视觉上大致轴对齐，rotation=0 与当前观察兼容，但尚未通过对应点量化确认。', '- example 0/1、2/3 同图呈现明显尺寸变化，存在 zoom 变化；精确 scale 范围、tx/ty 和不确定度尚无独立 landmark 标注，均为 unknown，不能用结构 bbox 比值冒充 scale。', '', '## 6. 重复、旧系统和数据边界', '', f'{len(refs)} 张单图 reference 无像素级完全重复；这不排除单人/双人图共享拓扑、重编码、局部重复或近重复。所有图像的精确重复组见 JSON。旧产物不自动纳入数据集。', '', '- 可直接使用的纯数据：两套原始图库的单图；examples 截图及配对图（仅评估标签核验）。总览仅用于人工核查。', '- 根目录 example0.png / example2.png / example4.png：仅列为未核验原图候选，其重复关系见 JSON，不自动增加样本数。', '- `plugin/` 下的 matcher、retrieval、registration、features、jiaye、probe、benchmark 全部隔离，不导入或复制。尤其 `mapid_v2.py` 虽带 v2 命名仍属旧系统。', '- `plugin/cache/`、`plugin/out/`、`out/regmap_bench/`、`_preview/`、旧 overlay 和 live 输出是历史派生数据；文件名预测不是 GT。', '- `out/known_poses.json` 等历史标注仅盘点路径，未加载或采信；后续如使用，需独立确认坐标系、来源和误差。', '', '旧 benchmark 文件：', '']
lines += ['- `' + p + '`' for p in d['legacy_benchmarks']]
lines += ['', f"既有 Python 文件共 {len(d['legacy_python'])} 个，完整列表见 JSON。未修改旧代码。", '', '## 7. Baseline 计划与门槛', '', '详见 ../../mapmatching/benchmarks/README.md：先独立楼层和对应点标注，验证跨域局部结构，然后建立新局部检索 baseline；retrieval、GT-map registration 诊断和 final decision 分开评估。只评价可见 evidence，不以未见 reference 结构扣分。', '', '先比较局部边界/距离场与线段组合，不默认 ORB/AKAZE 有效。不实现全图 MSE/SSIM，不将全候选多尺度 XY 穷举当成最终架构。消融分别检验标注去除、HUD 排除、空间一致性及单向验证。', '', '需扩充：未覆盖的 Hard 地图、Nightmare solo/duo、1F/2F/地下室、同图不同位置/尺度/fog、混淆图、无地图与严重遮挡负例；按 map 分组避免同图开发/测试泄漏。', '', '## 8. 当前结果', '', '| Metric | Result |', '|---|---:|', '| Top-1 / Top-3 / Top-5 | N/A — baseline 未运行 |', '| Floor / Scale / Translation / Full pose | N/A — 独立 GT 未建立 |', '| UNKNOWN / Wrong-lock | N/A — 未实现 final decision |', f"| 审计扫描与统计时间 | {d['audit_runtime_seconds']:.3f} s |", '| Matcher runtime | N/A |', '', '审计时间不包含联系表生成，也不是 matcher cold-start。当前环境 OpenCV 4.13.0、NumPy 2.3.5。', '', '复现：`python mapmatching/audit.py` 然后 `python mapmatching/write_report.py`。本轮停在 Phase 0，不宣称解决 Map ID 或泛化能力。']
(OUT / 'data_audit.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
if (OUT / 'baseline.json').exists() and json.loads((OUT / 'baseline.json').read_text(encoding='utf-8')).get('status') != 'PLANNED_NOT_RUN':
    print('Wrote historical audit; preserved measured baseline results. Use benchmarks.report for the current report.')
    raise SystemExit(0)
(OUT / 'baseline.json').write_text(json.dumps({'status': 'PLANNED_NOT_RUN', 'reason': 'User requested stop after data audit', 'top1': None, 'top3': None, 'top5': None, 'floor_accuracy': None, 'scale_error': None, 'translation_error': None, 'full_pose_error': None, 'unknown_rate': None, 'wrong_lock_rate': None, 'runtime_ms': None, 'evaluated_samples': 0}, indent=2), encoding='utf-8')
(OUT / 'baseline.md').write_text('# Baseline — planned, not run\n\n按需求末尾指示，完成 Data Audit 后停止。指标均为 N/A；无 baseline 实测。\n\n计划见 [新评估方案](../../mapmatching/benchmarks/README.md)，真实数据见 [审计报告](data_audit.md)。\n', encoding='utf-8')
print('Wrote data_audit.md, visual_annotations.json, baseline.md/json')
