"""硬门：新的 maps/evidence/*.npz 必须与迁移前的特征**逐字节相同**。

为什么这是整次重构最重要的一条：识别行为有没有被动过，只有它能证明。
图的字节没变、`extract()` 的阈值没动、`exclude_regions` 没动 → 特征就该一模一样。
任何一张不等，都说明我在搬家的路上顺手改了识别 —— 停下来查，不要往下走。

跑法：
    python scripts/compare_evidence.py
"""
from pathlib import Path
import json
import sys
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT/'out/_refactor_backup'
MAPS = ROOT/'maps'
KEYS = ('mask', 'boundary', 'corners', 'descriptors', 'radii', 'distance')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load(path):
    with np.load(path, allow_pickle=False) as a:
        return {k: a[k] for k in KEYS}


def diff(name, old, new):
    """返回第一处不同的人话描述，全同返回 None。"""
    for key in KEYS:
        a, b = old[key], new[key]
        if a.shape != b.shape:
            return f'{key} 形状 {a.shape} -> {b.shape}'
        if a.dtype != b.dtype:
            return f'{key} 类型 {a.dtype} -> {b.dtype}'
        if not a.tobytes() == b.tobytes():
            bad = int(np.argmax(np.any(a.reshape(a.shape[0], -1) != b.reshape(b.shape[0], -1), axis=1))) \
                if a.ndim > 1 and a.shape[0] else 0
            return f'{key} 内容不同（{int((a != b).sum())} 个元素，首个在 [{bad}]）'
    return None


def main():
    old_index = read_json(BACKUP/'index_backup/index.json')
    new_index = read_json(MAPS/'index.json')
    new_records = {r['map_id']: r for r in new_index['references']}

    # 旧的 map_id -> 旧 npz。用**备份里那份 index.json**，不是新索引 —— 这样
    # 连「我有没有把某张图的 map_id 改错」都能一并查出来。
    pairs, missing = [], []
    for record in old_index['references']:
        old = BACKUP/'index_backup'/record['array']
        new_record = new_records.get(record['map_id'])
        if new_record is None:
            missing.append(record['map_id'])
            continue
        pairs.append((f"内置 {record['map_id']}", old, MAPS/'evidence'/new_record['array']))

    # 5 张自建图：map_id 变了（custom/... -> <难度>/<名字>），靠 floors.json 里的
    # review 字段回溯到原来那个 uuid 目录。
    for entry in read_json(MAPS/'floors.json')['references']:
        review = entry.get('review', '')
        if not review.startswith('迁移自 user_maps/'):
            continue
        identity = review.split('/')[-1]
        new_record = new_records.get(entry['map_id'])
        if new_record is None:
            missing.append(entry['map_id'])
            continue
        pairs.append((f"自建 {entry['map_id']}",
                      BACKUP/'user_maps_backup'/identity/'evidence.npz',
                      MAPS/'evidence'/new_record['array']))

    print(f'新索引 {len(new_index["references"])} 条，可比对 {len(pairs)} 对')
    if missing:
        print(f'\n!! 新索引里找不到这些 map_id：')
        for map_id in missing:
            print(f'   {map_id}')
    failures = []
    for name, old_path, new_path in pairs:
        if not old_path.exists():
            failures.append((name, f'旧特征不存在：{old_path}'))
            continue
        if not new_path.exists():
            failures.append((name, f'新特征不存在：{new_path}'))
            continue
        problem = diff(name, load(old_path), load(new_path))
        if problem:
            failures.append((name, problem))
    print(f'逐字节相同：{len(pairs) - len(failures)} / {len(pairs)}\n')
    for name, problem in failures:
        print(f'FAIL  {name}\n      {problem}')
    if failures or missing:
        raise SystemExit(f'\n硬门没过：{len(failures)} 张特征不同，{len(missing)} 张丢失。')
    print('硬门通过：59 张特征与迁移前逐字节相同，识别行为没有被碰过。')


if __name__ == '__main__':
    main()
