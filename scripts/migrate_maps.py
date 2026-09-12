"""一次性迁移：把散落的原图收进 maps/，并合成 maps/floors.json。

**这个脚本已经跑完了（2026-09-12），它读的那三个旧图片目录已经被删掉。**
留在这里只是为了让「`maps/floors.json` 是怎么来的」有据可查；
再跑一次会在 `collect()` 里报「找不到 index.json」然后退出，不会改坏任何东西。

跑法（务必先 --check）：
    python scripts/migrate_maps.py --check     # 只读，打印将要做什么，校验 sha256
    python scripts/migrate_maps.py --apply     # 真的建目录、拷文件、写 floors.json

跑完之后的那道硬门在 `scripts/compare_evidence.py`：新的 `maps/evidence/*.npz`
必须与迁移前的 54 + 5 份特征**逐字节相同**。那是「识别行为没被碰过」的唯一证据，
结果 59/59 通过。

设计约束（每一条都有原因，别顺手改）：
- **只复制、不移动、不重编码**。原图字节必须逐字节保持不变：
  `benchmarks/benchmark.py` 靠 `examples/N/*.jpg` 与索引记录的 **sha256 精确配对**，
  文件被重编码或改名会让 7 个样例静默变成 skipped、指标全变 null。
- **map_id 和 source 显式写进 floors.json，不从路径反推**：
  `nightmare/duo/北-Z1门 ` 的 map_id 里带着一个尾随空格（文件名里也有），
  任何「按路径拼 map_id」的写法都会在它身上错开。
- 内置 54 张不给 `include_regions`（它们靠 `exclude_regions`，与今天完全一致）；
  迁移过来的 5 张给 `include_regions`（复现 add_map 当年在全分辨率下做的掩膜）。
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

# 控制台是 UTF-8，但 Python 默认按 cp936 编码输出，中文会变成乱码。
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT/'mapmatching/reference'
MAPS = ROOT/'maps'
OVERVIEW = '一图流'                     # 总览图，从来不进索引，不搬


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixel_sha256(path):
    """解码后的像素哈希，与 add_map 存进 record.json 的 pixel_sha256 同口径。"""
    import cv2
    import numpy as np
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f'图片解不开：{path}')
    return hashlib.sha256(image.tobytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload):
    # cp936 机器上漏掉 encoding 会把中文 map_id/source 写成乱码。
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def subdir(difficulty, mode):
    return difficulty if not mode else f'{difficulty}/{mode}'


def collect():
    """算出「谁搬到哪」，顺便把该有的校验全做掉。返回 (entries, copies, orphans)。"""
    index = read_json(REF/'index/index.json')
    floors = read_json(REF/'floor_regions.json')
    layouts = {r['map_id']: r for r in floors['references']}

    entries, copies, orphans = [], [], []
    seen_source, seen_id = {}, set()

    # ---- 1) 内置 54 张：图在三个旧文件夹里，元数据在 floor_regions.json ----
    for record in index['references']:
        map_id = record['map_id']
        old = Path(record['source'])
        layout = layouts.get(map_id)
        if layout is None:
            raise SystemExit(f'内置 {map_id} 在 floor_regions.json 里没有条目，停下来查')
        name = old.name
        if OVERVIEW in name:
            raise SystemExit(f'{map_id} 是总览图，不该出现在索引里')
        relative = f"maps/{subdir(record['difficulty'], record['mode'])}/{name}"
        if relative in seen_source:
            raise SystemExit(f'两张图会撞到同一个目标路径：{relative}')
        seen_source[relative] = map_id
        seen_id.add(map_id)
        source = ROOT/old
        digest = sha256_file(source)
        # 这是「没有重编码」的硬证据：floor_regions.json 记的正是原文件字节的 sha256
        if digest != layout['source_sha256']:
            raise SystemExit(f'{map_id} 的文件哈希与 floor_regions.json 对不上')
        copies.append((source, ROOT/relative))
        entries.append(dict(map_id=map_id, name=Path(name).stem,
                            difficulty=record['difficulty'], mode=record['mode'],
                            source=relative, sha256=digest, size=layout['size'],
                            regions=layout['regions'], exclude_regions=layout['exclude_regions'],
                            review=layout.get('review', '')))

    # ---- 2) 自建 5 张：原图搬到对应难度，楼层框原样保留并镜像成 include_regions ----
    user_root = REF/'user_maps'
    for record_path in sorted(user_root.glob('*/record.json')):
        record = read_json(record_path)
        name, difficulty, mode = record['name'], record['difficulty'], record['mode']
        map_id = f"{subdir(difficulty, mode)}/{name}"
        if map_id in seen_id:
            raise SystemExit(f'迁移后的 map_id 与内置撞车：{map_id}')
        seen_id.add(map_id)
        relative = f"maps/{subdir(difficulty, mode)}/{name}.png"
        if relative in seen_source:
            raise SystemExit(f'两张图会撞到同一个目标路径：{relative}')
        seen_source[relative] = map_id
        source = record_path.parent/'original.png'
        digest = sha256_file(source)
        # add_map 存的是无损 PNG 重编码，所以这张的 sha256 与 record.json 里的
        # pixel_sha256（像素哈希，不是文件哈希）本来就是两回事，这里只记文件哈希。
        copies.append((source, ROOT/relative))
        entries.append(dict(map_id=map_id, name=name, difficulty=difficulty, mode=mode,
                            source=relative, sha256=digest, size=record['size'],
                            regions=record['regions'], exclude_regions=[],
                            include_regions=[r['bbox'] for r in record['regions']],
                            review=f"迁移自 user_maps/{record_path.parent.name}"))

    # ---- 3) 09.10 里那些**没有**被录入过的图：留着，但不进 floors.json ----
    # 去重必须按**像素**而不是按文件名：上游是 .jpg、迁移过来的是 .png，
    # 光看名字 5 张重复的全都躲得过检查，然后以「近似重复的图」形态混进 maps/。
    # record.json 里的 pixel_sha256 正是用来做这件事的。
    known_pixels = {read_json(p)['pixel_sha256'] for p in user_root.glob('*/record.json')}
    builtin_bytes = {e['sha256'] for e in entries if 'include_regions' not in e}
    legacy = ROOT/'09.10更新'
    if legacy.is_dir():
        for path in sorted(legacy.rglob('*')):
            if path.suffix.lower() not in ('.jpg', '.jpeg', '.png') or OVERVIEW in path.name:
                continue
            if sha256_file(path) in builtin_bytes:
                continue
            if pixel_sha256(path) in known_pixels:
                continue        # 与某张已迁移的图逐像素相同，只留迁移的那份
            orphans.append((path, ROOT/f"maps/_unindexed/{path.name}"))

    return entries, copies, orphans


def report(entries, copies, orphans):
    print(f'内置 + 迁移条目：{len(entries)}')
    for difficulty, mode in (('hard', None), ('nightmare', 'solo'), ('nightmare', 'duo')):
        got = [e for e in entries if e['difficulty'] == difficulty and e['mode'] == mode]
        print(f'  {subdir(difficulty, mode):<18} {len(got):>3} 张')
    migrated = [e for e in entries if 'include_regions' in e]
    print(f'其中带 include_regions（原自建）：{len(migrated)}')
    print(f'待复制文件：{len(copies)}')
    print(f'不登记、单独存放：{len(orphans)}')
    for source, target in orphans:
        print(f'  {source.name}  ->  {target.relative_to(ROOT).as_posix()}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='只校验，不写盘')
    parser.add_argument('--apply', action='store_true', help='真的执行')
    args = parser.parse_args()
    if args.check == args.apply:
        raise SystemExit('二选一：--check 或 --apply')

    entries, copies, orphans = collect()
    report(entries, copies, orphans)

    if args.check:
        print('\nCHECK OK：全部哈希对得上，没有路径冲突。没有写任何东西。')
        return

    for _, target in copies + orphans:
        target.parent.mkdir(parents=True, exist_ok=True)
    for source, target in copies + orphans:
        if target.exists():
            raise SystemExit(f'目标已存在，拒绝覆盖：{target}')
        shutil.copyfile(source, target)
        if sha256_file(source) != sha256_file(target):
            raise SystemExit(f'复制后哈希不一致：{target}')
    write_json(MAPS/'floors.json', dict(
        schema_version=2,
        scope='maps/ 下所有已录入的地图；entry 存在即参与匹配，缺 include_regions 表示用 exclude_regions',
        references=entries))
    print(f'\nAPPLY 完成：{len(copies) + len(orphans)} 个文件已就位，maps/floors.json 已写。')
    print('旧目录一个都没删 —— 等特征逐字节比对通过之后再删。')


if __name__ == '__main__':
    main()
