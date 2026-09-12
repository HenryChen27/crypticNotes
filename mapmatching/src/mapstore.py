"""`maps/` 目录的读写：登记表、特征、索引。

    maps/
    ├─ hard/   nightmare/{solo,duo}/   原图。文件名 = 地图名，字节原样，绝不重编码。
    ├─ _unindexed/                     放进来但**没有登记的**图，不参与匹配。
    ├─ floors.json                     登记表 + 楼层几何。**唯一手工维护的文件。**
    ├─ index.json                      派生物：抽取结果缓存（factor / 校验用哈希）
    ├─ disabled.json                   被移除的登记条目，原样存放，恢复就是搬回去
    └─ evidence/<16hex>.npz            派生物：每张图一份特征

**核心不变式**：`maps/<难度>/[<人数>/]<名字>.<后缀>` 里有图，且 `floors.json` 里有同名条目
= 已录入、进索引。只有图没有条目 = 只是躺着，不参与匹配。这条同时实现了
「粘贴进目录不会被自动识别」和「新图必须走 UI 录入」。

**为什么不用「全局哈希」当索引闸门**（原 `floor_metadata_sha256` 的做法）：
`floors.json` 现在是**活的用户数据** —— 录入一张图改它、软删除一张图也改它。
全局哈希意味着任何一次增删都会让整个索引作废、逼一次 1~3 分钟的全量重建。
改成**逐图闸门**（`entry_sha`）之后，增删都只是清单搬移，索引原地不动。
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os
import tempfile
import uuid
import cv2
import numpy as np
from .evidence import extract
from .types import Evidence
from mapmatching.config import fingerprint

VERSION = 5
REMOVE_ANNOTATIONS = True

# 影响**特征**的字段。只改 review / name 不该让索引作废，改几何就必须作废。
EVIDENCE_FIELDS = ('source', 'sha256', 'regions', 'exclude_regions', 'include_regions')


def maps_dir(root) -> Path:
    return Path(root).resolve()/'maps'


def _root_of(maps: Path) -> Path:
    """maps/ 的父目录就是 ROOT —— floors.json 里的 source 是相对 ROOT 的路径，
    这样 `live.py` 那句 `read_image(root/ref.source)` 一行都不用改。"""
    return Path(maps).resolve().parent


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Cannot decode image: {path}')
    return image


# ---- json ---------------------------------------------------------------
def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, payload):
    """`ensure_ascii=False` + `encoding='utf-8'` 必须成对出现。
    本机 `locale.getpreferredencoding()` 是 cp936，漏掉 encoding 会把中文
    map_id / source 写成乱码，症状是「文件明明在却报找不到」。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.tmp-', suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


# ---- 登记表 --------------------------------------------------------------
def read_manifest(maps) -> list[dict]:
    payload = _read_json(Path(maps)/'floors.json', None)
    if not isinstance(payload, dict) or not isinstance(payload.get('references'), list):
        return []
    return [e for e in payload['references'] if isinstance(e, dict) and e.get('map_id')]


def write_manifest(maps, entries):
    write_json(Path(maps)/'floors.json', dict(
        schema_version=2,
        scope='maps/ 下所有已录入的地图；有条目即参与匹配，缺 include_regions 表示按 exclude_regions 取特征',
        references=list(entries)))


def read_disabled(maps) -> list[dict]:
    payload = _read_json(Path(maps)/'disabled.json', None)
    if not isinstance(payload, dict) or not isinstance(payload.get('records'), list):
        return []
    return [e for e in payload['records'] if isinstance(e, dict) and e.get('map_id')]


def read_disabled_positions(maps) -> dict[str, int]:
    """被移除的条目**原来待在 floors.json 的第几位**。

    没有这个，「移除再恢复」就只能把条目追加到末尾：用户看到的是那张图莫名
    跳到列表最后一位，而且 `floors.json` 的顺序变了，`index.json` 会跟着重排 ——
    并列候选的先后也就跟着变。记的是**移除那一刻的绝对下标**，所以中间又移除/
    恢复了别的图时会差几位（插入前会夹回范围内，不会报错），够用且不用维护锚点。
    坏值和不认识的 map_id 一律丢掉，当作「没记过」。
    """
    payload = _read_json(Path(maps)/'disabled.json', None)
    raw = payload.get('positions') if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    alive = {e['map_id'] for e in read_disabled(maps)}
    return {k: v for k, v in raw.items()
            if k in alive and isinstance(v, int) and not isinstance(v, bool) and v >= 0}


def write_disabled(maps, entries, positions=None):
    write_json(Path(maps)/'disabled.json',
               dict(version=1, records=list(entries), positions=dict(positions or {})))


def live_entries(maps) -> list[dict]:
    """参与匹配的条目 = 登记表里的全部，顺序不变。

    被移除的条目**不在这里**，它们只存在于 disabled.json。恢复就是搬回来。
    `disabled.json` 与 `floors.json` 求交集那套自愈规则见 `set_map_enabled`。
    """
    return read_manifest(maps)


# ---- 特征 ----------------------------------------------------------------
def evidence_name(map_id: str) -> str:
    """由 map_id 派生的文件名。JSON 里因此**不存任何文件路径** ——
    路径穿越的攻击面直接消失，而且增删一张图不会重排其它图的文件名。"""
    return hashlib.sha256(map_id.encode('utf-8')).hexdigest()[:16] + '.npz'


def entry_sha(entry: dict) -> str:
    payload = json.dumps({k: entry.get(k) for k in EVIDENCE_FIELDS},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def mask_outside(image: np.ndarray, boxes) -> np.ndarray:
    """把框**外**清零。

    这是原来 `map_library.add_map` 在全分辨率下做的事，搬到这里来是为了让
    `build_index()` 能逐字节复现它。**不能**改用 `extract(exclude_regions=…)` 代替：
    那个是在 `cv2.resize` **之后**清零的，和「先清零再缩放」在边界上差一个像素，
    实测 5 张里会有 1 张的 corners/descriptors 全部漂移。
    """
    keep = np.zeros(image.shape[:2], bool)
    for x0, y0, x1, y1 in boxes or []:
        keep[y0:y1, x0:x1] = True
    return image*keep[:, :, None]


def _safe_source(root: Path, entry: dict) -> Path:
    """`source` 是 JSON 里唯一一个会变成文件路径的字段，必须卡住。"""
    raw = str(entry.get('source') or '')
    if not raw or Path(raw).is_absolute() or '..' in Path(raw).parts:
        raise ValueError(f'条目里的 source 不合法：{entry.get("map_id")}')
    resolved = (root/raw).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f'条目里的 source 越界：{entry.get("map_id")}')
    return resolved


def materialize(maps, entry: dict) -> dict:
    """把（原图 + 楼层几何）变成（特征 npz + 索引记录）。**唯一的一条路**，
    `build_index()` 和录入都走它 —— 两条路各写各的，迟早会漂移。"""
    maps = Path(maps)
    root = _root_of(maps)
    source = _safe_source(root, entry)
    image = read_image(source)
    if entry.get('include_regions'):
        image = mask_outside(image, entry['include_regions'])
    evidence = extract(image, reference=True, remove_annotations=REMOVE_ANNOTATIONS,
                       exclude_regions=entry.get('exclude_regions') or None)
    if len(evidence.corners) < 4:
        # 这条以前长在 `map_library.add_map` 里。挪过来是为了让「登记一张图」和
        # 「重建索引」共用同一道检查 —— 否则一张抽不出结构的图会安静地进索引，
        # 然后在匹配时空转。
        raise ValueError(f'选区内缺少可识别的地图结构，请使用清晰完整的地图原图：{entry.get("map_id")}')
    distance = cv2.distanceTransform(1-evidence.boundary, cv2.DIST_L2, 3)

    directory = maps/'evidence'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/evidence_name(entry['map_id'])
    temp = directory/f'.tmp-{uuid.uuid4().hex}.npz'
    try:
        np.savez_compressed(temp, mask=evidence.mask, boundary=evidence.boundary,
                            corners=evidence.corners, descriptors=evidence.descriptors,
                            radii=evidence.radii, distance=distance)
        os.replace(temp, target)          # 半截的 npz 绝不能被 load() 看见
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return dict(map_id=entry['map_id'], array=target.name, factor=evidence.image_factor,
                sha256=entry.get('sha256'), entry_sha=entry_sha(entry))


def build_index(maps, *, force: bool = False) -> None:
    """重建索引。没变过的条目直接复用旧记录（加一张图不必重跑全量）。"""
    maps = Path(maps)
    previous = {}
    if not force:
        payload = _read_json(maps/'index.json', None)
        if isinstance(payload, dict) and payload.get('version') == VERSION \
                and payload.get('config_fingerprint') == fingerprint() \
                and payload.get('remove_annotations') == REMOVE_ANNOTATIONS:
            previous = {r['map_id']: r for r in payload.get('references', []) if isinstance(r, dict)}
    records = []
    for entry in live_entries(maps):
        cached = previous.get(entry['map_id'])
        fresh = (cached is not None
                 and cached.get('sha256') == entry.get('sha256')
                 and cached.get('entry_sha') == entry_sha(entry)
                 and (maps/'evidence'/str(cached.get('array'))).exists())
        records.append(cached if fresh else materialize(maps, entry))
    write_json(maps/'index.json', dict(version=VERSION, config_fingerprint=fingerprint(),
                                       remove_annotations=REMOVE_ANNOTATIONS, references=records))


def load_references(maps, *, difficulty=None, mode=None) -> list:
    from .reference import Reference      # 延迟导入：reference 在函数体里反向引用本模块
    maps = Path(maps)
    payload = _read_json(maps/'index.json', None)
    if payload is None:
        raise ValueError('Rebuild incompatible index')
    if payload.get('version') != VERSION or payload.get('config_fingerprint') != fingerprint() \
            or payload.get('remove_annotations') != REMOVE_ANNOTATIONS:
        raise ValueError('Rebuild incompatible index')
    records = {r['map_id']: r for r in payload.get('references', []) if isinstance(r, dict)}
    result = []
    for entry in live_entries(maps):
        if difficulty is not None and entry['difficulty'] != difficulty:
            continue
        if mode is not None and entry['mode'] != mode:
            continue
        record = records.get(entry['map_id'])
        if record is None or record.get('entry_sha') != entry_sha(entry):
            raise ValueError(f'Rebuild index: {entry["map_id"]}')
        array = maps/'evidence'/str(record.get('array'))
        if not array.exists():
            raise ValueError(f'Rebuild index: {entry["map_id"]}')
        with np.load(array, allow_pickle=False) as a:
            evidence = Evidence(a['mask'], a['boundary'], a['corners'], a['descriptors'],
                                a['radii'], record['factor'], None)
            result.append(Reference(entry['map_id'], entry['difficulty'], entry['mode'],
                                    entry['source'], evidence, a['distance'],
                                    entry.get('regions', []), entry.get('exclude_regions', [])))
    return result


def set_map_enabled(maps, map_id: str, enabled: bool) -> dict:
    """移除 / 恢复一张地图。**对内置和自建一视同仁** —— 只是把登记条目在
    floors.json 和 disabled.json 之间搬，原图和特征文件原地不动。

    两次写入的**顺序是刻意的**：永远先写「让这条记录更存在」的那个文件。
    中途崩掉会留下「两边都有」的状态，而 `live_entries` 以 floors.json 为准，
    判定为可用 —— 自愈，不会出现「两边都没有」这种彻底丢失。
    """
    maps = Path(maps)
    entries = read_manifest(maps)
    disabled = read_disabled(maps)
    positions = read_disabled_positions(maps)
    present = next((e for e in entries if e.get('map_id') == map_id), None)
    stashed = next((e for e in disabled if e.get('map_id') == map_id), None)
    if enabled:
        if stashed is None:
            if present is not None:
                return present            # 已经在登记表里，无事可做
            raise ValueError('找不到这张地图')
        # 回到移除前的位置，而不是追加到末尾（见 read_disabled_positions）。
        at = positions.pop(map_id, None)
        rest = [e for e in disabled if e.get('map_id') != map_id]
        if present is not None:
            kept = entries                # 崩溃后「两边都有」，登记表已经是对的
        elif at is None:
            kept = entries+[stashed]
        else:
            kept = entries[:at]+[stashed]+entries[at:]
        write_manifest(maps, kept)        # 先写「更存在」的那个
        write_disabled(maps, rest, positions)
        return stashed
    if present is None:
        raise ValueError('找不到这张地图')
    rest = disabled if stashed is not None else disabled+[present]
    kept = [e for e in entries if e.get('map_id') != map_id]
    if stashed is None:
        positions[map_id] = next(i for i, e in enumerate(entries) if e.get('map_id') == map_id)
    write_disabled(maps, rest, positions)  # 先写「更存在」的那个
    write_manifest(maps, kept)
    return present
