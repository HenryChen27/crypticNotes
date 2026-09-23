"""Local diagnostic cases with bounded oldest-first retention."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform
import time
import uuid
import shutil
import cv2


def category(result, error=None):
    if error:
        return '程序异常'
    if result.get('reason') == 'map_ui_not_confirmed':
        return '未确认地图展开'
    candidates = result.get('candidates', [])
    if not candidates:
        return '未发现地图结构'
    c = candidates[0]
    if not c.get('pose'):
        return '无法配准'
    if (c.get('explained') or 0) < .55 or (c.get('contradiction') if c.get('contradiction') is not None else 1) > .40 or c.get('retrieval_score', 0) < 4:
        return '匹配证据不足'
    if len(candidates) > 1 and (c.get('explained') or 0) - (candidates[1].get('explained') or 0) < .01:
        return '候选地图相似'
    if c.get('floor') is None:
        return '楼层不确定'
    return '叠图生成失败'


class FailureRecorder:
    def __init__(self, directory, root, max_cases=20, max_bytes=500*1024**2):
        self.directory = Path(directory)
        self.max_cases, self.max_bytes = max(1, max_cases), max_bytes
        self.last = {}
        root = Path(root)
        sources = sorted((root/'mapmatching/src').glob('*.py'))
        self.version = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [root/'maps/floors.json', *sources] if p.is_file()}

    def prune(self):
        root = self.directory.resolve()
        for group in self.directory.iterdir() if self.directory.exists() else []:
            if not group.is_dir() or group.is_symlink():
                continue
            records = sorted(group.glob('*/record.json'), key=lambda p: p.parent.name)
            size = sum(p.stat().st_size for p in group.rglob('*') if p.is_file())
            while records and (len(records) > self.max_cases or size > self.max_bytes):
                folder = records.pop(0).parent
                resolved = folder.resolve()
                if not resolved.is_relative_to(root) or resolved == root or folder.is_symlink():
                    raise ValueError('Unsafe record directory')
                size -= sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
                shutil.rmtree(folder)

    def save(self, pixels, result, context, message, error=None, success=False):
        try:
            self.prune()
            kind = '识别成功' if success and not error else category(result, error)
            # Exact-image duplicate suppression and a per-category cooldown.
            digest = hashlib.sha256(pixels.tobytes()).hexdigest()
            now = time.monotonic()
            previous = self.last.get(kind)
            if previous and (now-previous[0] < 30 or digest == previous[1]):
                return '重复或短时间连续失败，已跳过'
            ok, png = cv2.imencode('.png', pixels)
            if not ok:
                return '截图编码失败'
            data = dict(schema_version=2, time=datetime.now(timezone.utc).isoformat(),
                        app_version='2026.09.23-input', outcome='accepted' if success else 'rejected',
                        category=kind, message=message, error=error,
                        context=context, screenshot_sha256=digest,
                        image_shape=list(pixels.shape), result=result,
                        versions=self.version, platform=platform.platform(), opencv=cv2.__version__)
            encoded = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode('utf-8')
            if png.nbytes+len(encoded) > self.max_bytes:
                return '单条记录过大，已跳过'
            folder = self.directory/kind/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
            folder.mkdir(parents=True)
            (folder/'screen.png').write_bytes(png.tobytes())
            (folder/'record.json').write_bytes(encoded)
            self.prune()
            self.last[kind] = (now, digest)
            return '已保存识别记录'
        except Exception:
            # Disk / serialization failures must never break recognition.
            return '失败记录写入失败，请检查空间和目录权限'
