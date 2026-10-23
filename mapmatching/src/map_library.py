"""把一张图**登记**进 `maps/`：复制原图、写登记条目、抽特征、挂进索引。

原来的做法是给每张自建图开一个 `user_maps/<uuid>/` 目录、塞一整套
（原图 + record.json + evidence.npz），索引再把这些目录 glob 出来接在内置图后面。
现在没有「自建」这个概念了 —— 内置和自建躺在同一棵树里、进同一张表，
`add_map` 要做的事就只剩「登记」：把图放进 `maps/<难度>[/<人数>]/`，
在 `floors.json` 里加一条，把特征抽出来。**唯一仍由 UI 把关的是这一步** ——
往 `maps/` 里粘贴文件不会让任何东西进索引（见 `mapstore` 的核心不变式）。
"""
from pathlib import Path
import hashlib
import json
import os
import uuid
from .context import SessionContext
from .reference import read_image
from . import mapstore
from .map_image import compact, scale_entry_geometry, POLICY

# 一张图被登记时允许的后缀。和 reference.py 当年扫目录时的白名单一致。
SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def validate_regions(regions, width, height):
    if not regions:
        raise ValueError('请至少框选一个楼层')
    seen=set()
    for r in regions:
        floor=r['floor']
        box=r['bbox']
        if floor not in (-1,1,2) or floor in seen:
            raise ValueError('每个楼层只能标注一次')
        seen.add(floor)
        if len(box)!=4 or any(type(v) is not int for v in box):
            raise ValueError('楼层坐标必须为整数')
        x0,y0,x1,y1=box
        if not (0<=x0<x1<=width and 0<=y0<y1<=height) or min(x1-x0,y1-y0)<20:
            raise ValueError('楼层选区太小或超出原图')
    # Compact source layouts may interleave floors. Preserve overlapping boxes
    # exactly as marked; each floor still has its own independently saved crop.


def validate_name(name):
    name=name.strip()
    if not name or len(name)>60 or any(c in name for c in '/\\\n\r'):
        raise ValueError('请输入 1–60 字的地图名称，不包含斜杠或换行')
    if name.startswith('.'):
        raise ValueError('地图名称不能以点开头')
    return name


def _target_for(maps, source, name, difficulty, mode, provider='lianghapi'):
    """Return a safe import destination; compression may change the suffix."""
    suffix=Path(source).suffix.lower()
    if suffix not in SUFFIXES:
        raise ValueError('只支持 PNG / JPG / WebP / BMP 格式的地图')
    if Path(source).resolve().is_relative_to(maps.resolve()):return Path(source).resolve()
    directory=maps/provider/difficulty
    if mode:
        directory=directory/mode
    return directory/f'{name}{suffix}'


def _fingerprints(maps):
    """现有全部条目的字节哈希与像素哈希，用来拦重复录入。"""
    entries=mapstore.live_entries(maps)+mapstore.read_disabled(maps)
    return ({v for e in entries for v in (e.get('sha256'), e.get('storage',{}).get('original_sha256')) if v},
            {v for e in entries for v in (e.get('pixel_sha256'), e.get('storage',{}).get('original_pixel_sha256')) if v})


def add_map(root, source, name, difficulty, mode, regions, provider='lianghapi'):
    root=Path(root).resolve()
    SessionContext(difficulty,mode,provider)
    name=validate_name(name)
    maps=mapstore.maps_dir(root)
    source=Path(source).resolve()
    original=read_image(source)
    h,w=original.shape[:2]
    validate_regions(regions,w,h)
    map_id=f'{difficulty}/'+(f'{mode}/' if mode else '')+name
    if provider == 'zhanshi':map_id='zhanshi/'+map_id
    library=mapstore.live_entries(maps)
    disabled=mapstore.read_disabled(maps)
    if any(e['map_id']==map_id for e in library+disabled):
        raise ValueError('这个模式下已有同名地图，请勿重复录入')
    raw=source.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    pixel=hashlib.sha256(original.tobytes()).hexdigest()
    known_bytes,known_pixels=_fingerprints(maps)
    if digest in known_bytes or pixel in known_pixels:
        raise ValueError('这个模式下已有相同图片的地图，请勿重复录入')
    encoded,suffix,pixels,ratios=compact(original,raw,source.suffix)
    converted=encoded!=raw
    target=_target_for(maps,source,name,difficulty,mode,provider)
    if converted:
        directory=maps/provider/difficulty
        if mode: directory=directory/mode
        target=directory/f'{name}{suffix}'
        # Never overwrite a user's input, even if it is already inside maps/.
        if target.resolve()==source:
            target=directory/f'{name}.compact{suffix}'
    geometry=scale_entry_geometry(dict(regions=regions,include_regions=[r['bbox'] for r in regions]),ratios,(pixels.shape[1],pixels.shape[0]))
    validate_regions(geometry['regions'],pixels.shape[1],pixels.shape[0])
    stored_pixel=hashlib.sha256(pixels.tobytes()).hexdigest()
    if stored_pixel in known_pixels:
        raise ValueError('这个模式下已有相同图片的地图，请勿重复录入')
    if target.exists() and target.resolve()!=source:
        raise ValueError(f'maps 目录下已有同名文件：{target.name}')

    lock=maps/'.import.lock'
    maps.mkdir(parents=True,exist_ok=True)
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        raise ValueError('另一个地图正在保存，请稍后重试')
    copied=target.resolve()!=source
    try:
        os.close(fd)
        if copied:
            target.parent.mkdir(parents=True,exist_ok=True)   # maps/<难度>/[<人数>/] 可能还不存在
            pending=target.with_name(target.name+'.import-'+uuid.uuid4().hex)
            try:
                pending.write_bytes(encoded)
                os.replace(pending,target)
            finally:
                pending.unlink(missing_ok=True)
        # 手绘的楼层框一物二用：`regions` 给叠图定位用，`include_regions` 给特征提取用
        # （在全分辨率下把框外清零，见 `mapstore.mask_outside` 里为什么必须这样）。
        entry=dict(map_id=map_id,name=name,difficulty=difficulty,mode=mode,
                   source=target.relative_to(root).as_posix(),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                   pixel_sha256=stored_pixel,size=geometry['size'],regions=geometry['regions'],exclude_regions=[],
                   include_regions=geometry['include_regions'],review='')
        if converted:
            entry['storage']=dict(policy=POLICY,original_size=[w,h],original_sha256=digest,original_pixel_sha256=pixel,resize=list(ratios))
        entry['provider']=provider
        if provider == 'zhanshi':entry['reference_style']='zhanshi-v1'
        recognition_path=None
        try:
            if converted:
                original_entry=dict(entry,regions=regions,include_regions=[r['bbox'] for r in regions])
                recognition_path=maps/'recognition-inputs'/mapstore.evidence_name(map_id).replace('.npz','.png')
                entry['recognition']=mapstore.recognition_input(maps,original_entry,original,ratios)
            # 挂索引走 `build_index` 而不是自己往 index.json 里塞一条：它是增量的，
            # 没变过的 58 张直接复用旧记录，只抽这一张；而且顺手把「索引文件不存在 /
            # 版本过期 / 别的图几何改过」这几种情况一并修好 —— 自己塞一条的话，
            # 这三种里任何一种都会让新图当场挂不上去。
            mapstore.write_manifest(maps,library+[entry])
            mapstore.build_index(maps)
        except BaseException:
            mapstore.write_manifest(maps,library)   # 抽特征失败就退回登记前，不留半截状态
            if copied:
                target.unlink(missing_ok=True)
            if recognition_path is not None:
                recognition_path.unlink(missing_ok=True)
            (maps/'evidence'/mapstore.evidence_name(map_id)).unlink(missing_ok=True)
            raise
        return entry
    finally:
        lock.unlink(missing_ok=True)
