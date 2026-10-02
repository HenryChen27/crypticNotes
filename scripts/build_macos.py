"""Build a self-contained macOS application and ZIP on a real macOS runner."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable,'-m','mapmatching','build-index','--index',str(ROOT/'maps')],
                   cwd=ROOT,check=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir',
          '--name','加页手记','--paths',str(ROOT),
          '--hidden-import','mapmatching.portable_check',
          '--hidden-import','ScreenCaptureKit',
          '--osx-bundle-identifier','com.henrychen.crypticnotes',
          '--distpath',str(ROOT/'dist-macos'),'--workpath',str(ROOT/'build/pyinstaller-macos'),
          '--specpath',str(ROOT/'build')]
    for module in ('torch','tensorflow','matplotlib','pandas','IPython','pytest','notebook','tkinter','win32gui','win32api','win32ui','win32con'):
        args += ['--exclude-module',module]
    data=[ROOT/'mapmatching/assets',ROOT/'docs/images',
          *(ROOT/'maps'/name for name in ('hard','nightmare','_unindexed','evidence','floors.json','index.json','disabled.json','README.md')),
          ROOT/'README.md']
    data.extend(p for p in (ROOT/'mapmatching/appearance/skins').rglob('*')
                if p.is_file() and p.suffix.lower() in ('.png','.jpg','.webp','.json'))
    data.extend((ROOT/'mapmatching').glob('*.md'))
    for path in data:
        if path.exists():
            destination=path.relative_to(ROOT) if path.is_dir() else path.parent.relative_to(ROOT)
            args += ['--add-data',f'{path}{os.pathsep}{destination}']
    args.append(str(ROOT/'mapmatching/launch.py'))
    subprocess.run(args,cwd=ROOT,check=True)

    app=ROOT/'dist-macos/加页手记.app'
    if not app.is_dir():
        raise SystemExit(f'App bundle not generated: {app}')
    release=ROOT/'release'; release.mkdir(exist_ok=True)
    arch=os.environ.get('MACOS_ARCH','arm64')
    archive=release/f'IdentityVMapAssistant-macOS-{arch}.zip'
    if archive.exists(): archive.unlink()
    # Preserve executable bits and the .app bundle layout. ditto is available
    # on every supported macOS runner and produces Finder-compatible ZIPs.
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(archive)],check=True)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (release/f'macos-{arch}-SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(f'macOS ZIP: {archive.stat().st_size/1024**2:.1f} MiB')


if __name__=='__main__': main()
