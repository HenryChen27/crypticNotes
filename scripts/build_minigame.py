"""Build an optional game ZIP including its independent WebEngine runtime."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--tag', default='desktop-v1.0.0')
    args = parser.parse_args()
    source = args.source.resolve()
    for name in ('index.html', 'assets', 'js', 'css'):
        if not (source/name).exists():
            raise SystemExit('Missing game source: ' + name)
    key = 'windows-x64' if sys.platform == 'win32' else 'macos-' + ('arm64' if platform.machine() == 'arm64' else 'x64')
    destination = ROOT/'out/minigames'/key
    if destination.exists():
        raise SystemExit('Output already exists; move the previous build before rebuilding: ' + str(destination))
    destination.mkdir(parents=True)
    env = os.environ.copy()
    if sys.platform == 'win32':
        windows = Path(env.get('SystemRoot', r'C:\Windows'))
        env['PATH'] = os.pathsep.join(map(str, (Path(sys.executable).parent, windows/'System32', windows)))
    command = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir', '--windowed',
               '--name', 'Jellyfish', '--distpath', str(destination), '--workpath', str(ROOT/'build/minigames'/key),
               '--specpath', str(ROOT/'build/minigames')]
    if sys.platform == 'darwin':
        command += ['--osx-bundle-identifier','com.henrychen.jellyfish.desktop']
    for module in ('numpy', 'scipy', 'cv2', 'torch', 'tensorflow', 'matplotlib', 'pandas', 'IPython', 'tkinter'):
        command += ['--exclude-module', module]
    command.append(str(ROOT/'scripts/minigame_runner.py'))
    subprocess.run(command, env=env, check=True)
    if sys.platform == 'darwin':
        import build_macos
        build_macos.BUNDLE_ID = 'com.henrychen.jellyfish.desktop'
        keychain = os.environ.get('MACOS_KEYCHAIN','')
        identity = build_macos.signing_identity(keychain)
        app = destination/'Jellyfish.app'
        build_macos.sign(app,identity,keychain)
        build_macos.verify(app,identity)
    for name in ('index.html', 'assets', 'js', 'css'):
        target = destination/'game'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if (source/name).is_dir():
            shutil.copytree(source/name, target, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store', '*.mp4', '*.MP4'))
        else:
            shutil.copy2(source/name, target)
    metadata = {'id': 'jellyfish', 'name': '合成大水母', 'version': args.version, 'platform': key}
    (destination/'package.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    bundle = destination.parent / f'Jellyfish-{key}.zip'
    # The macOS app is the executable payload; avoid an unused duplicate onedir.
    files = [p for p in destination.rglob('*') if (p.is_file() or p.is_symlink())
             and not (sys.platform == 'darwin' and p.relative_to(destination).parts[0] == 'Jellyfish')]
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path.relative_to(destination).as_posix())
            info.create_system = 3
            info.external_attr = path.lstat().st_mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, os.readlink(path).encode() if path.is_symlink() else path.read_bytes())
    with bundle.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    catalog_path = destination.parent/'desktop-games.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {'schema': 1, 'id': 'jellyfish', 'packages': {}}
    catalog['packages'][key] = {'version': args.version, 'size': bundle.stat().st_size, 'sha256': checksum,
        'url': f'https://github.com/HenryChen27/Jellyfish/releases/download/{args.tag}/{bundle.name}'}
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Game package:', bundle)
    print('Download catalog:', catalog_path)


if __name__ == '__main__':
    main()
