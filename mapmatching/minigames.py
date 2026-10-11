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


def read_catalog(url=CATALOG_URL, game_id=GAME_ID):
    request = urllib.request.Request(url, headers={'User-Agent': 'IdentityVMapAssistant-games'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError('小游戏下载清单过大')
    catalog = json.loads(raw)
    if catalog.get('schema') not in (1, 2) or catalog.get('id') != game_id:
        raise ValueError('小游戏下载清单格式不正确')
    return catalog


def package_info(catalog, key=None):
    info = catalog.get('packages', {}).get(key or platform_key())
    if catalog.get('schema') == 2:
        info = catalog.get('launchers', {}).get(key) if key else catalog.get('game')
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
    def __init__(self, data_root, game_id=GAME_ID, catalog_url=CATALOG_URL):
        if not game_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in game_id) or game_id == 'runtime':
            raise ValueError('小游戏名称不正确')
        self.game_id = game_id
        self.catalog_url = catalog_url
        self.root = Path(data_root) / 'minigames'
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def folder(self):
        return self.root / self.game_id

    def installed(self):
        try:
            metadata = json.loads((self.folder / 'package.json').read_text(encoding='utf-8'))
            return metadata.get('id') == self.game_id and self.entry().is_file() and (self.folder/'game/index.html').is_file()
        except (OSError, ValueError):
            return False

    def entry(self):
        try:
            metadata = json.loads((self.folder/'package.json').read_text(encoding='utf-8'))
            if metadata.get('runtime') == 'system-webview':
                return LauncherStore(self.root.parent).entry()
        except (OSError, ValueError):
            pass
        if sys.platform == 'darwin':
            return self.folder / 'Jellyfish.app/Contents/MacOS/Jellyfish'
        return self.folder / 'Jellyfish/Jellyfish.exe'

    def size(self):
        return sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file()) if self.folder.exists() else 0

    def native(self):
        try:
            return json.loads((self.folder/'package.json').read_text(encoding='utf-8')).get('runtime') == 'system-webview'
        except (OSError, ValueError):
            return False

    def install(self, archive, checksum, expected_size=None):
        archive = Path(archive)
        if expected_size is not None and archive.stat().st_size != expected_size:
            raise ValueError('小游戏包下载不完整')
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != checksum:
            raise ValueError('小游戏包校验失败，请重新下载')
        staging = Path(tempfile.mkdtemp(prefix='.install-', dir=self.root)).resolve()
        backup = self.root / ('.previous-' + self.folder.name)
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
                        app_name = getattr(self, 'app_name', 'Jellyfish.app')
                        if sys.platform != 'darwin' or path.parts[0] != app_name or item.file_size > 4096:
                            raise ValueError('小游戏包包含无效链接')
                        relative = bundle.read(item).decode('utf-8')
                        link_target = (target.parent / relative).resolve()
                        if Path(relative).is_absolute() or not link_target.is_relative_to(staging/app_name):
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
                    app_name = getattr(self, 'app_name', 'Jellyfish.app')
                    if not (target.parent/relative).resolve().is_relative_to(staging/app_name):
                        raise ValueError('小游戏包包含越界链接')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(relative)
                for target, _ in links:
                    if not target.resolve().is_relative_to(staging/app_name):
                        raise ValueError('小游戏包包含越界链接')
            metadata = json.loads((staging/'package.json').read_text(encoding='utf-8'))
            self.validate_package(staging, metadata)
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

    def validate_package(self, staging, metadata):
        if metadata.get('id') != self.game_id or not (staging/'game/index.html').is_file():
            raise ValueError('小游戏包结构不正确')
        if metadata.get('runtime') == 'system-webview':
            if not LauncherStore(self.root.parent).installed():
                raise ValueError('公共小游戏启动器尚未安装')
            return
        relative_entry = (Path('Jellyfish.app/Contents/MacOS/Jellyfish') if sys.platform == 'darwin'
                          else Path('Jellyfish/Jellyfish.exe'))
        if metadata.get('platform') != platform_key() or not (staging/relative_entry).is_file():
            raise ValueError('小游戏包结构或系统不正确')

    def download(self, progress, cancelled=lambda: False):
        progress(0, '正在查询小游戏包…')
        catalog = read_catalog(self.catalog_url, self.game_id)
        if catalog.get('schema') == 2:
            launcher = LauncherStore(self.root.parent)
            launcher_info = package_info(catalog, platform_key())
            if not launcher.installed() or launcher.version() != launcher_info.get('version'):
                launcher.download_package(launcher_info,
                    lambda value, text: progress(value // 10, '正在安装公共小游戏启动器…'), cancelled)
            self.download_package(package_info(catalog),
                lambda value, text: progress(10 + value * 90 // 100, text), cancelled)
        else:
            self.download_package(package_info(catalog), progress, cancelled)

    def download_package(self, info, progress, cancelled=lambda: False):
        temporary = self.root / ('.' + self.folder.name + '-download.zip')
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


class LauncherStore(GameStore):
    app_name = 'GameLauncher.app'

    @property
    def folder(self):
        return self.root / 'runtime'

    def entry(self):
        return self.folder / ('GameLauncher.app/Contents/MacOS/GameLauncher' if sys.platform == 'darwin'
                              else 'GameLauncher.exe')

    def installed(self):
        try:
            metadata = json.loads((self.folder/'package.json').read_text(encoding='utf-8'))
            return metadata.get('id') == 'game-launcher' and metadata.get('platform') == platform_key() and self.entry().is_file()
        except (OSError, ValueError):
            return False

    def version(self):
        try:
            return json.loads((self.folder/'package.json').read_text(encoding='utf-8')).get('version')
        except (OSError, ValueError):
            return None

    def validate_package(self, staging, metadata):
        relative = self.entry().relative_to(self.folder)
        if metadata.get('id') != 'game-launcher' or metadata.get('platform') != platform_key() or not (staging/relative).is_file():
            raise ValueError('公共小游戏启动器结构或系统不正确')
