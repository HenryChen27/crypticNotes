"""Export reviewed source inputs, without local history, credentials or caches.

重新生成是幂等的：先按白名单清掉上一次的内容（保留 `.git`，那是分享仓库自己的
历史），再整份复制。否则从白名单里去掉的文件会一直留在上一次的产物里。
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]

# 「一图流」是给玩家看的总览大图（60+42+37 MB），没有任何一张进特征索引 ——
# reference.build 只扫逐张的门图。打包脚本本来就把它们排除在成品之外，
# 进 Git 只会让 clone 变慢并触发 GitHub 的大文件警告。
EXCLUDED_NAMES=('一图流',)


def keep(path, relative):
    if '__pycache__' in relative.parts or path.suffix in ('.pyc','.log','.lock'):
        return False
    # 派生产物，首次启动会自动重建：索引缓存与每张图的特征。
    # `floors.json` **不排除** —— 它是登记表，是源，不是派生物。
    if relative.as_posix().startswith(('maps/index.json','maps/evidence')):
        return False
    if relative.as_posix()=='maps/disabled.json':
        return False                    # 某台机器上的移除记录，属于本地状态，不往分享里带
    if any(part.startswith('.pending-') for part in relative.parts):
        return False                    # 录入中断留下的临时目录
    if any(token in path.name for token in EXCLUDED_NAMES):
        return False
    return True


def sweep(target):
    """清空上一次的产物，只留下分享仓库自己的 .git。"""
    if not target.exists():
        return
    for entry in target.iterdir():
        if entry.name=='.git':
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()


def main():
    target=ROOT/'release/crypticNotes'
    topfiles=['README.md','.gitignore','.gitattributes','requirements-build.txt']
    files=[ROOT/n for n in topfiles]+list(ROOT.glob('*.cmd'))
    directories=[ROOT/'mapmatching',ROOT/'maps',ROOT/'scripts',ROOT/'examples',ROOT/'docs',ROOT/'.github']
    for directory in directories:
        if not directory.exists():continue
        for path in directory.rglob('*'):
            if not path.is_file():continue
            if keep(path,path.relative_to(ROOT)):
                files.append(path)
    # **先清点再清空**：`sweep` 是不可逆的，如果某个白名单里的源文件不在
    # （顶层文件曾经就这么丢过一次），清完再复制会留下一个半空的分享仓库、
    # 而且看不出是哪一步坏的。缺文件就该一个字节都不动地停下。
    missing=[p for p in files if not p.is_file()]
    if missing:
        raise SystemExit('源文件缺失，未改动分享仓库：'+', '.join(str(p.relative_to(ROOT)) for p in missing))
    target.mkdir(parents=True,exist_ok=True)
    sweep(target)
    manifest=[]
    for path in files:
        relative=path.relative_to(ROOT)
        destination=target/relative; destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,destination)
        manifest.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (ROOT/'release/source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Prepared {len(files)} files, {sum(r["bytes"] for r in manifest)/1024**2:.1f} MiB')


if __name__=='__main__':main()
