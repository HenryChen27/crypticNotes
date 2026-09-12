"""Render measured results, keeping unknown metrics explicitly null/N/A."""
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root/'out/mapmatching'
    baseline = json.loads((out/'baseline.json').read_text(encoding='utf-8'))
    cold = json.loads((out/'cold_start.json').read_text(encoding='utf-8'))
    m = baseline['metrics']
    lines = ['# Progress — Map Matching v2 baseline', '', '## 1. What I inspected', '', '两套原始图库，54 张单图；6 张开发截图，4 个 Hard 身份；独立 evidence 和候选局部几何诊断。', '', '## 2. What I implemented', '', '全新 evidence、局部描述与稀疏投票检索、Top-5 局部配准、非对称边界验证、离线索引、benchmark、API/CLI、显式 session 生命周期。没有实际屏幕叠加，没有可靠 MATCHED/LOCK。', '', '## 3. Files changed', '', '`mapmatching/config.py`、`src/`、`benchmarks/`、`tests/`、CLI、README、TECHNICAL_PATH.md，以及 `out/mapmatching/` 新实验结果。旧代码未修改。', '', '## 4. Benchmark command', '', '```powershell', 'python -m mapmatching.benchmarks.benchmark --build', 'python -m mapmatching.benchmarks.benchmark --no-spatial --output out/mapmatching/ablation_no_spatial.json', 'python -m mapmatching.benchmarks.benchmark --no-hud --output out/mapmatching/ablation_no_hud.json', 'python -m mapmatching.benchmarks.benchmark --build --no-clean --index mapmatching/reference/index_no_clean --output out/mapmatching/ablation_no_clean.json', 'python -m mapmatching.benchmarks.cold_start', 'python -m mapmatching.benchmarks.diagnostics', 'python -m unittest discover -s mapmatching/tests -v', '```', '', '## 5. Results', '', '| Metric | Result |', '|---|---:|']
    for name, value in [('Retrieval Top-1', m['top1']), ('Retrieval Top-3', m['top3']), ('Retrieval Top-5', m['top5']), ('配准后第一候选正确率（非正式接受）', m['registered_top1']), ('UNKNOWN', m['unknown_rate'])]:
        lines.append(f'| {name} | {value:.2%} |')
    lines += ['| Floor / Scale / Translation / Full pose | N/A，无独立 GT |', '| Wrong-lock | 0/6，但接受数为 0，不代表可用 |', f"| Warm median / p95 | {m['warm_median_ms']:.1f} / {m['warm_p95_ms']:.1f} ms |", f"| Fresh-process median / p95 | {cold['median_ms']:.1f} / {cold['p95_ms']:.1f} ms |", '| Contract tests | 6 passed，合成测试不是实际图像正确率 |', '', 'Warm 不含图像解码和 imports；fresh-process 包含 imports/index/decode/inference/输出，未清空 OS 文件缓存。运行时单线程，seed=0。', '', '| Experiment | Top-1 | Top-3 | Top-5 | 配准后 Top-1 | Warm median ms |', '|---|---:|---:|---:|---:|---:|']
    for filename in ['baseline_initial.json', 'baseline.json', 'ablation_no_spatial.json', 'ablation_no_hud.json', 'ablation_no_clean.json']:
        d = json.loads((out/filename).read_text(encoding='utf-8'))['metrics']
        lines.append(f"| {filename} | {d['top1']:.2%} | {d['top3']:.2%} | {d['top5']:.2%} | {d['registered_top1']:.2%} | {d['warm_median_ms']:.1f} |")
    lines += ['', 'Initial 使用 V>=57 / S<=115；当前固定 V>=78 / S<=80，V<=170。这个修正来自开发集观察，不能视为独立测试提升。No-clean 禁用形态学及小洞清理，仍保留同一颜色阈值；No-spatial 只移除 retrieval 的空间支持排名，后续候选配准仍使用几何。', '', '## 6. Failure cases', '', '| Screenshot | GT | 检索名次 | 配准后第一候选 | Explained |', '|---|---|---:|---|---:|']
    for s in baseline['samples']:
        winner = s['candidates'][0]
        lines.append(f"| {s['screenshot']} | {s['gt_map']} | {s['retrieval_rank']} | {winner['map_id']} | {winner['explained']:.4f} |")
    lines += ['', 'example 3/4 的跨难度局部结构混淆。每例全部排名、候选 pose 及单独的 oracle GT-map registration 诊断见 JSON。oracle 不能进入生产推理。静态并排二值几何图见 geometry_diagnostics.png；它不是屏幕 overlay。', '', '## 7. Interpretation', '', '基本局部几何能将正确图召回，但身份决策尚不可靠。floor、插图排除、fog 分离和 pose 真值缺失；confidence/scale uncertainty 保持 null。当前不是能自动带路的成品插件。只在6张开发图上评估，Dataset coverage insufficient。', '', '## 8. Next hypothesis', '', '在独立楼层/插图区域和人工对应点基础上，比较带方向的稳定边界与占据矛盾能否减少局部混淆，同时扩充跨难度相似结构负例。技术路径见 ../../mapmatching/TECHNICAL_PATH.md。']
    (out/'baseline.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Wrote measured baseline.md')


if __name__ == '__main__':
    main()
