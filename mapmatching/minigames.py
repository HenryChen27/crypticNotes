"""Optional desktop game packages. No game engine is loaded by the companion."""
from __future__ import annotations
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

CATALOG_URL = 'https://github.com/HenryChen27/Jellyfish/releases/latest/download/desktop-games.json'
GAME_ID = 'jellyfish'
MAX_DOWNLOAD = 600 * 1024 * 1024
MAX_EXTRACTED = 1400 * 1024 * 1024


def platform_key():
    if sys.platform == 'win32':
        return 'windows-x64'
    if sys.platform == 'darwin':
        return 'macos-arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'macos-x64'
    raise ValueError('小游戏暂不支持此系统')


def read_catalog(url=CATALOG_URL):
    request = urllib.request.Request(url, headers={'User-Agent': 'IdentityVMapAssistant-games'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError('小游戏下载清单过大')
    catalog = json.loads(raw)
    if catalog.get('schema') != 1 or catalog.get('id') != GAME_ID:
        raise ValueError('小游戏下载清单格式不正确')
    return catalog


def package_info(catalog, key=None):
    info = catalog.get('packages', {}).get(key or platform_key())
    if not info:
        raise ValueError('该系统的小游戏包尚未上架')
    url = info.get('url', '')
    if not url.startswith('https://github.com/HenryChen27/Jellyfish/releases/download/'):
        raise ValueError('小游戏下载地址不正确')
    checksum = info.get('sha256', '')
    if len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
        raise ValueError('小游戏包缺少校验信息')
    if not isinstance(info.get('size'), int) or not 0 < info['size'] <= MAX_DOWNLOAD:
        raise ValueError('小游戏包大小不正确')
    return info


class GameStore:
    def __init__(self, data_root):
        self.root = Path(data_root) / 'minigames'
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def folder(self):
        return self.root / GAME_ID

    def installed(self):
        try:
            metadata = json.loads((self.folder / 'package.json').read_text(encoding='utf-8'))
            return metadata.get('id') == GAME_ID and self.entry().is_file() and (self.folder/'game/index.html').is_file()
        except (OSError, ValueError):
            return False

    def entry(self):
        if sys.platform == 'darwin':
            return self.folder / 'Jellyfish.app/Contents/MacOS/Jellyfish'
        return self.folder / 'Jellyfish/Jellyfish.exe'

    def size(self):
        return sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file()) if self.folder.exists() else 0

    def install(self, archive, checksum, expected_size=None):
        archive = Path(archive)
        if expected_size is not None and archive.stat().st_size != expected_size:
            raise ValueError('小游戏包下载不完整')
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != checksum:
            raise ValueError('小游戏包校验失败，请重新下载')
        staging = Path(tempfile.mkdtemp(prefix='.install-', dir=self.root))
        backup = self.root / '.previous-jellyfish'
        try:
            with zipfile.ZipFile(archive) as bundle:
                total = 0
                names = set()
                links = []
                for item in bundle.infolist():
                    name = item.filename.replace('\\', '/')
                    path = PurePosixPath(name)
                    mode = item.external_attr >> 16
                    if (path.is_absolute() or '..' in path.parts or ':' in name
                            or name.casefold() in names):
                        raise ValueError('小游戏包包含无效路径')
                    names.add(name.casefold())
                    total += item.file_size
                    if total > MAX_EXTRACTED or len(names) > 20000:
                        raise ValueError('小游戏包解压大小超出限制')
                    target = staging.joinpath(*path.parts)
                    if stat.S_ISLNK(mode):
                        # Signed macOS bundles need their framework symlinks.
                        # Create these last, and only inside this game's app.
                        if sys.platform != 'darwin' or path.parts[0] != 'Jellyfish.app' or item.file_size > 4096:
                            raise ValueError('小游戏包包含无效链接')
                        relative = bundle.read(item).decode('utf-8')
                        link_target = (target.parent / relative).resolve()
                        if Path(relative).is_absolute() or not link_target.is_relative_to(staging/'Jellyfish.app'):
                            raise ValueError('小游戏包包含越界链接')
                        links.append((target, relative))
                        continue
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(item) as source, target.open('wb') as destination:
                            shutil.copyfileobj(source, destination)
                        if sys.platform == 'darwin' and mode:
                            target.chmod(mode & 0o777)
                for target, relative in links:
                    if not (target.parent/relative).resolve().is_relative_to(staging/'Jellyfish.app'):
                        raise ValueError('小游戏包包含越界链接')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(relative)
                for target, _ in links:
                    if not target.resolve().is_relative_to(staging/'Jellyfish.app'):
                        raise ValueError('小游戏包包含越界链接')
            metadata = json.loads((staging/'package.json').read_text(encoding='utf-8'))
            relative_entry = self.entry().relative_to(self.folder)
            if (metadata.get('id') != GAME_ID or metadata.get('platform') != platform_key()
                    or not (staging/relative_entry).is_file() or not (staging/'game/index.html').is_file()):
                raise ValueError('小游戏包结构或系统不正确')
            if backup.exists():
                shutil.rmtree(backup)
            if self.folder.exists():
                self.folder.rename(backup)
            try:
                staging.rename(self.folder)
            except OSError:
                if backup.exists():
                    backup.rename(self.folder)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def download(self, progress, cancelled=lambda: False):
        progress(0, '正在查询小游戏包…')
        info = package_info(read_catalog())
        temporary = self.root / '.jellyfish-download.zip'
        try:
            request = urllib.request.Request(info['url'], headers={'User-Agent': 'IdentityVMapAssistant-games'})
            with urllib.request.urlopen(request, timeout=45) as response, temporary.open('wb') as output:
                received = 0
                while block := response.read(256 * 1024):
                    if cancelled():
                        raise InterruptedError('已取消下载')
                    received += len(block)
                    if received > info['size']:
                        raise ValueError('小游戏包大小超出下载清单')
                    output.write(block)
                    progress(min(95, received * 95 // info['size']), '正在下载…')
            if cancelled():
                raise InterruptedError('已取消下载')
            progress(96, '正在校验并安装…')
            self.install(temporary, info['sha256'], info['size'])
            progress(100, '下载完成')
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self):
        target = self.folder
        if target.is_symlink() or target.resolve().parent != self.root.resolve():
            raise ValueError('小游戏目录路径不正确')
        if target.exists():
            shutil.rmtree(target)
