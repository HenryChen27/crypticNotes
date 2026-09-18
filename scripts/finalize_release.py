"""Retain notices and produce the complete-folder ZIP plus a checksum."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import shutil
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from dist_extras import inject

ROOT=Path(__file__).resolve().parents[1]


def finalize():
    for directory in (ROOT/'.ui-deps',ROOT/'.build-deps'):
        if directory.exists():sys.path.insert(0,str(directory))
    product=ROOT/'dist/IdentityVMapAssistant'
    # **先清点再复制**：这些顶层文件都不在版本库里（`dist/` 和 `release/` 都 gitignore，
    # 它们是每次现场生成的产品文件），丢了就只能靠 `release/` 里那份老提交找回来。
    # 不先查一遍的话，PyInstaller 已经跑完 90 秒，最后死在一句
    # `FileNotFoundError [WinError 2]` 上，看不出缺的是哪个文件。
    wanted=('README.md',)
    missing=[n for n in wanted if not (ROOT/n).is_file()]
    if missing:
        raise SystemExit('顶层文件缺失，未生成发布目录：'+', '.join(missing))
    for name in wanted:
        shutil.copy2(ROOT/name,product/name)
    for path in (ROOT/'mapmatching').glob('*.md'):
        shutil.copy2(path,product/'mapmatching'/path.name)
    for name in ('numpy','scipy','opencv-python','PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','pywin32','psutil','pyinstaller'):
        distribution=metadata.distribution(name)
        for entry in distribution.files or []:
            if '.dist-info/' not in entry.as_posix():continue
            source=Path(distribution.locate_file(entry))
            if source.is_file():
                target=product/'third-party'/entry
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copy2(python_license,product/'third-party/Python-LICENSE.txt')
    # 更新入口必须在**压缩之前**注入：它们不属于 PyInstaller 的产物，打包不会带上，
    # 而 zip 是从成品目录直接压出来的。漏掉的后果是拿到 zip 的协作者没有更新按钮
    # —— 上一版 zip 就这么发出去过（578 个文件里一个更新入口都没有）。
    # 具体拷贝和编码校验都在 dist_extras 里，publish_dist.sh 走的是同一个函数。
    inject(product)
    release=ROOT/'release'; release.mkdir(exist_ok=True)
    archive=release/'IdentityVMapAssistant-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(product.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(product.parent).as_posix())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (release/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(f'Portable ZIP: {archive.stat().st_size/1024**2:.1f} MiB')


if __name__=='__main__':finalize()
