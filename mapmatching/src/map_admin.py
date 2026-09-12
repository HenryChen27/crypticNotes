"""地图目录的浏览与增删。**刻意站在识别路径之外。**

这个模块只读写 `maps/floors.json`、`maps/disabled.json`、`maps/index.json`，
不 import evidence / matcher / retrieval，也不碰 `reference.py` 的加载逻辑。
所以「识别逻辑」保持逐字节不变。

**内置和自建不再有区别。** 以前内置走软删除、自建走真删（原图是凉的、自建的
是用户自己塞的）；现在所有图都躺在 `maps/` 这一棵树里，删谁的语义都一样：
把登记条目从 `floors.json` 搬进 `disabled.json`，**原图和特征原地不动**。
搬到哪一步都只是搬条目，所以「删掉」永远是瞬时的、可恢复的。
"""
from pathlib import Path
import os
from . import mapstore

FLOOR_TEXT = {1: '1F', 2: '2F', -1: '地下室'}
MODE_TEXT = {None: '', 'solo': '单人', 'duo': '多人'}


def maps_dir(root):
    return mapstore.maps_dir(root)


def floor_text(floors):
    return '·'.join(FLOOR_TEXT.get(f, f'{f}F') for f in floors)


def context_text(difficulty, mode):
    if difficulty == 'hard':
        return '困难'
    return f'噩梦·{MODE_TEXT.get(mode, "")}'


def _floors(regions):
    """1F/2F 在前、地下室在后 —— 和录入界面的楼层选择器同序。"""
    seen = {r['floor'] for r in regions or [] if isinstance(r, dict) and 'floor' in r}
    return sorted(seen, key=lambda f: (f == -1, f))


def _stale_ids(maps):
    """`floors.json` 改了但索引还没跟上时，这一张需要重建索引。

    这是原来那条**全局** `floor_metadata_sha256` 闸的替代品。那条闸的问题是
    `floors.json` 现在是活数据：录入一张、移除一张都会改它，于是整个索引被判过期、
    逼一次全量重建。逐图比对 `entry_sha` 之后，只有真正动过几何的那一张会被标出来。
    这里**只标不改** —— 列表页不该顺手重建索引，那是几十秒到几分钟的事。
    """
    payload = mapstore._read_json(maps/'index.json', None)
    if not isinstance(payload, dict):
        return None                       # 索引还没建，整页都算待重建
    records = {r['map_id']: r for r in payload.get('references', []) if isinstance(r, dict)}
    stale = set()
    for entry in mapstore.live_entries(maps):
        record = records.get(entry['map_id'])
        if record is None or record.get('entry_sha') != mapstore.entry_sha(entry):
            stale.add(entry['map_id'])
    return stale


def _row(entry, state, writable, stale):
    map_id = str(entry.get('map_id', ''))
    return dict(map_id=map_id, name=entry.get('name') or map_id.split('/')[-1],
                difficulty=entry.get('difficulty'), mode=entry.get('mode'),
                floors=_floors(entry.get('regions')), state=state, stale=stale,
                writable=writable, source=entry.get('source'),
                regions=entry.get('regions') or [])


def list_maps(root):
    """当前能匹配到的每一张，加上被移除的每一张。

    只读 `floors.json` / `disabled.json` / `index.json` 三个小文件，不碰
    `evidence/*.npz` —— 既省掉几十 MB 的解压，也让「某一张的几何过期了」只是
    把那一行标成待重建，而不是把整页带崩。
    """
    maps = maps_dir(root)
    writable = os.access(maps, os.W_OK)
    stale = _stale_ids(maps)
    rows = [_row(e, 'active', writable, stale is None or e['map_id'] in stale)
            for e in mapstore.live_entries(maps)]
    live = {e['map_id'] for e in mapstore.live_entries(maps)}
    # 自愈：两边都有的条目以 `floors.json` 为准，不在这里重复列一遍
    # （`set_map_enabled` 的写入顺序保证崩溃只会留下「两边都有」，不会两边都没有）。
    rows.extend(_row(e, 'disabled', writable, False)
                for e in mapstore.read_disabled(maps) if e['map_id'] not in live)
    return rows


def set_enabled(root, map_id, enabled):
    """移除 / 恢复一张地图。任何一张都走这条路，没有例外。"""
    maps = maps_dir(root)
    if not os.access(maps, os.W_OK):
        raise ValueError('程序目录不可写，无法修改地图库；请把程序解压到可写目录后重试')
    return mapstore.set_map_enabled(maps, map_id, enabled)
