"""地图目录管理。delete_map 永久删除库内文件及登记。

set_enabled 保留兼容旧版停用数据，管理界面使用永久删除。
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


def delete_map(root, map_id):
    """永久删除登记、库内原图和特征；共享原图保留给其他条目。"""
    maps = maps_dir(root).resolve()
    entries = mapstore.read_manifest(maps)
    disabled = mapstore.read_disabled(maps)
    targets = [e for e in entries + disabled if e['map_id'] == map_id]
    if not targets:
        raise ValueError('找不到这张地图')
    others = [e for e in entries + disabled if e['map_id'] != map_id]
    shared = {mapstore._safe_source(maps.parent, e) for e in others}
    files = set()
    for entry in targets:
        source = mapstore._safe_source(maps.parent, entry)
        if not source.is_relative_to(maps) or source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            raise ValueError('原图不在地图库内，拒绝删除')
        if source not in shared:
            files.add(source)
    evidence = (maps/'evidence'/mapstore.evidence_name(map_id)).resolve()
    if not evidence.is_relative_to(maps):
        raise ValueError('特征文件路径越界，拒绝删除')
    files.add(evidence)
    metadata = [maps/'floors.json', maps/'disabled.json', maps/'index.json']
    # 出错时还原本次操作，不把删到一半当作成功；成功后不留回收副本。
    snapshot = {p: p.read_bytes() if p.exists() else None for p in files | set(metadata)}
    try:
        for path in files:
            path.unlink(missing_ok=True)
        mapstore.write_manifest(maps, [e for e in entries if e['map_id'] != map_id])
        positions = mapstore.read_disabled_positions(maps)
        positions.pop(map_id, None)
        mapstore.write_disabled(maps, [e for e in disabled if e['map_id'] != map_id], positions)
        index = mapstore._read_json(maps/'index.json', None)
        if index is not None:
            index['references'] = [e for e in index.get('references', []) if e['map_id'] != map_id]
            mapstore.write_json(maps/'index.json', index)
    except Exception:
        for path, content in snapshot.items():
            if content is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != content:
                path.write_bytes(content)
        raise
    return targets[0]
