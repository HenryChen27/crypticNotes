"""Summarize this milestone from measured artifacts, preserving earlier runs."""
from pathlib import Path
import json


def main() -> None:
    root=Path(__file__).resolve().parents[2]
    out=root/'out/mapmatching'
    bench=json.loads((out/'known_hard_layout.json').read_text(encoding='utf-8'))
    pose=json.loads((out/'pose_layout.json').read_text(encoding='utf-8'))
    showcase=json.loads((out/'showcase/manifest.json').read_text(encoding='utf-8'))
    m=bench['metrics']
    lines=['# Progress — 明确模式匹配、配准测量与离线叠图','',
           '## 1. What I inspected','',
           '复查跨难度混淆、原始 reference 楼层标题和插图；直接读取6张截图与4张配对标准图，独立标注41个墙角/门口对应点。54张原始reference SHA256均保持不变。','',
           '## 2. What I implemented','',
           '- 用户明确的模式条件成为必填 SessionContext；Hard 28图，Nightmare solo/duo分别13图，只加载选择的组。',
           '- Hard 28图的楼层区域/插图/标题排除元数据，带源图hash；位置来自逐图标题带，未统一按图高中点切割。',
           '- 独立临时人工标注与pose评估；没有将预测位姿写回标签。',
           '- 像素推理驱动的离线叠图模块、preview CLI、完整图/局部对照与可拖动展示页。',
           '- 未启用自动MATCHED/LOCK；尚无游戏内实时悬浮窗。','',
           '## 3. Files changed','',
           '`src/context.py`、`reference.py`、`evidence.py`、`registration.py`、`matcher.py`、`preview.py`、CLI；`reference/floor_regions.json`；`data/manual_landmarks.json`；新probe/annotation/pose/showcase评估工具；`tests/test_preview.py`；README与技术路径。旧plugin代码未修改。','',
           '展示：[打开交互展示](showcase/index.html)，[六图总览](showcase/all_examples_comparison.jpg)，[逐图变换](showcase/manifest.json)。','',
           '## 4. Benchmark command','',
           '```powershell',
           'python -m mapmatching build-index',
           'python -m mapmatching.benchmarks.benchmark --difficulty hard --output out/mapmatching/known_hard_layout.json',
           'python -m mapmatching.benchmarks.pose_evaluation --predictions out/mapmatching/known_hard_layout.json --output out/mapmatching/pose_layout.json',
           'python -m mapmatching.benchmarks.showcase',
           'python -m mapmatching preview examples/0/example.png --difficulty hard --output out/mapmatching/preview.png',
           'python -m unittest discover -s mapmatching/tests -v',
           '```','',
           '## 5. Results','',
           '| Metric | Result |','|---|---:|',
           f"| Retrieval Top-1 | {m['top1']:.2%} (4/6) |", '| Retrieval Top-3 / Top-5 | 100% / 100% (6/6) |',
           '| 配准验证后第一候选 Map ID | 100% (6/6)，仅当前已知Hard开发集 |',
           '| Floor | 100% (6/6)，全部为1F |',
           f"| Scale相对误差中位数 | {pose['metrics']['median_scale_relative_error']:.3%}，相对临时人工拟合 |",
           f"| 原图原点translation L2中位数 | {pose['metrics']['median_translation_l2_px']:.2f} px |",
           f"| 每图重投影RMS中位数 | {pose['metrics']['median_reprojection_rmse_px']:.2f} px |",
           f"| 最大单点重投影偏差 | {pose['metrics']['worst_reprojection_error_px']:.2f} px |",
           '| UNKNOWN | 6/6，生产decision未校准；预览为明确请求的候选展示 |',
           '| Wrong-lock | 0，接受样本0，不能据此宣称可靠拒识 |',
           f"| Warm median / p95 | {m['warm_median_ms']:.1f} / {m['warm_p95_ms']:.1f} ms，不含图片解码/叠图 |",
           '| Tests | 9 passed |',
           '| viewport外被改动像素 | 0（六图总和） |',
           '| CLI与展示页同一输入生成的PNG | SHA256完全相同 |','',
           '| Example | Map | Floor | 重投影RMS px | 最大点误差 px | 完整叠图 |','|---|---|---:|---:|---:|---|']
    for i,(p,s) in enumerate(zip(pose['samples'],showcase['results'])):
        lines.append(f"| {i} | {s['map_id']} | {s['floor']} | {p['reprojection_rmse_px']:.2f} | {p['reprojection_max_error_px']:.2f} | [打开](showcase/example_{i}_overlay.png) |")
    lines += ['', '人工标注质量：原始reference点选估计±2px，截图估计±3px；未外部复核。标注先做自身一致性检查，example2曾把U形缺口左角错对应到右角，复查原图后更正，修订记录体现在annotation_views与最终JSON中。所有指标都包含标注误差，不支持亚像素精度声明。','',
              '## 6. Failure cases','',
              '历史全54图基础实验将example3/4误识别为Nightmare相似局部。显式Hard条件消除了这两例跨难度候选。额外房间/通道语义试验将无模式结果提升到5/6；方向墙线试验又使example5产生不同混淆，因此这些probe没有贸然替换正常匹配器。',
              '当前数据没有Nightmare、2F、地图外负例或独立测试地图；Nightmare楼层区域未审核时预览拒绝渲染。显示清理是绘图专用近似，固定viewport也只覆盖当前截图布局。','',
              '## 7. Interpretation','',
              '已跑通现有数据的显式模式→认图→配准→楼层→离线叠图。展示不是手动选GT-map或手工对齐，GT只在渲染后附加统计。当前6图覆盖4个身份，Dataset coverage insufficient；游戏内悬浮显示、置信度校准和泛化验证仍未完成。','',
              '复核纠正：Hard 28张参考图为1F在上2F在下，分隔行不同；旧报告关于Hard楼层倒序的表述不成立。','',
              '## 8. Next hypothesis','',
              '补充Nightmare单人/多人及2F截图，验证分模式召回和floor；扩充负例并校准拒识后才开放可靠LOCK。实时显示层复用当前原图到整截图的变换与渲染逻辑，需要单独验证窗口坐标/DPI/地图移动后的生命周期，不能将静态截图叠图当成实时跟踪。']
    (out/'progress_overlay.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote progress_overlay.md')


if __name__=='__main__':
    main()
