"""一次性：把误登记为困难的「左 - 竖L门（09.10更新）」改到噩梦·单人。

`map_id` 由路径决定，改了 id 就等于换了身份 —— 特征文件名 `evidence_name(map_id)`
也跟着变，所以必须重新抽一次特征，并把旧的那份 npz 删掉，否则会在
`maps/evidence/` 里留一个永远没人引用的孤儿。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapmatching.src import mapstore

ROOT = Path(__file__).resolve().parents[1]
OLD_ID = 'hard/左 - 竖L门（09.10更新）'
NAME, DIFFICULTY, MODE = '左 - 竖L门（09.10更新）', 'nightmare', 'solo'


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    maps = mapstore.maps_dir(ROOT)
    entries = mapstore.read_manifest(maps)
    entry = next((e for e in entries if e['map_id'] == OLD_ID), None)
    if entry is None:
        print(f'登记表里没有 {OLD_ID}，可能已经改过了'); return 0

    new_id = f'{DIFFICULTY}/{MODE}/{NAME}'
    source = maps/'hard'/f'{NAME}.png'
    target = maps/DIFFICULTY/MODE/f'{NAME}.png'
    if not source.exists():
        print(f'原图不在预期位置：{source}'); return 1
    if target.exists():
        print(f'目标位置已有同名文件，拒绝覆盖：{target}'); return 1

    old_npz = maps/'evidence'/mapstore.evidence_name(OLD_ID)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    print(f'原图  {source.relative_to(ROOT)}  ->  {target.relative_to(ROOT)}')

    entry.update(map_id=new_id, difficulty=DIFFICULTY, mode=MODE,
                 source=target.relative_to(ROOT).as_posix())
    mapstore.write_manifest(maps, [entry if e['map_id'] == OLD_ID else e for e in entries])
    print(f'登记  {OLD_ID}  ->  {new_id}')

    # 只重建这一张：其余条目的 sha256 和 entry_sha 都没变，会被原样复用。
    mapstore.build_index(maps)
    new_npz = maps/'evidence'/mapstore.evidence_name(new_id)
    print(f'特征  {new_npz.name}  ({new_npz.stat().st_size} 字节)')

    if old_npz != new_npz and old_npz.exists():
        old_npz.unlink()
        print(f'清掉孤儿特征  {old_npz.name}')

    live = {mapstore.evidence_name(e['map_id']) for e in mapstore.live_entries(maps)}
    orphans = sorted(p.name for p in (maps/'evidence').glob('*.npz') if p.name not in live)
    print(f'\n索引 {len(live)} 条；evidence/ 里剩余孤儿：{orphans or "无"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
