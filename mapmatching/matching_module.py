"""The notes runtime owns the little-doll library; author packs own only official maps."""
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.request import Request, urlopen
import zipfile

from . import module_payload
from .distribution import module_info
from .paths import DATA_ROOT
from .src.provider_packages import PROVIDERS, change


class MatchingModule:
    def __init__(self, provider=None):
        if provider not in (None, 'original', *PROVIDERS):
            raise ValueError('未知地图版本')
        self.provider = provider
        self.key = provider if provider in PROVIDERS else 'notes'
        self.folder = DATA_ROOT/'modules/mapmatching'
        self.latest = None

    def root(self):
        return module_payload.folder(DATA_ROOT, 'notes') if self.key == 'notes' else self.folder

    def receipt(self):
        if self.key == 'notes':
            return module_payload.receipt(DATA_ROOT, 'notes')
        try:
            return json.loads((self.folder/'maps/packages'/f'{self.key}.json').read_text(encoding='utf8'))
        except (OSError, ValueError):
            return {}

    def enabled(self):
        return bool(self.receipt().get('sha256')) and (self.key == 'notes' or MatchingModule().enabled())

    def author_enabled(self, provider):
        return MatchingModule(provider).enabled()

    def version(self):
        spec = self.receipt()
        return spec.get('version') or spec.get('sha256','')[:12] or '未安装'

    def update_available(self):
        self.latest = module_info(self.key)
        return self.latest['sha256'] != self.receipt().get('sha256')

    def download(self, progress, cancelled=lambda: False):
        if self.key != 'notes' and not MatchingModule().enabled():
            raise ValueError('请先下载加页手记主程序')
        spec = self.latest = module_info(self.key)
        size, sha = spec['size'], spec['sha256']
        if not 0 < size <= 600*1024**2:
            raise ValueError('地图包大小异常')
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp)/'package.zip'
            count = 0
            with urlopen(Request(spec['url'],headers={'User-Agent':'CrypticNotes-modules'}),timeout=45) as source, archive.open('wb') as output:
                while block := source.read(256*1024):
                    if cancelled():raise InterruptedError('已取消下载')
                    count += len(block)
                    if count > size:raise ValueError('地图包大小异常')
                    output.write(block);progress(count*85//size,'正在下载地图包…')
            previous = self.receipt().get('sha256')
            if self.key == 'notes':
                module_payload.install(DATA_ROOT,'notes',archive,size,sha)
            else:
                if count != size or module_payload.digest(archive) != sha:raise ValueError('地图库校验失败')
                stage = Path(temp)/'maps'
                with zipfile.ZipFile(archive) as bundle:
                    seen = set();total = 0
                    for item in bundle.infolist():
                        name = item.filename;parts = PurePosixPath(name).parts;total += item.file_size
                        if (not parts or parts[0] != 'maps' or len(parts)<2 or '..' in parts or ':' in name or '\\' in name
                            or name.casefold() in seen or (item.external_attr>>16)&0o170000 == 0o120000
                            or len(seen)>=20000 or total>1400*1024**2):raise ValueError('无效地图库')
                        seen.add(name.casefold());bundle.extract(item,temp)
                if not (stage/'floors.json').is_file():raise ValueError('缺少地图库清单')
                retained=DATA_ROOT/'module-user-data/mapmatching/maps'
                if not (self.folder/'maps').exists() and retained.is_dir():shutil.copytree(retained,self.folder/'maps')
                change(self.folder,self.key,stage,dict(provider=self.key,size=size,sha256=sha))
            from . import package_stats
            package_stats.installed(self.key, previous, sha, self.receipt().get('version'))
            progress(100,'安装完成')

    def delete(self):
        if self.provider == 'original':raise ValueError('小布偶随加页手记安装')
        if self.key == 'notes':
            for provider in PROVIDERS:
                if MatchingModule(provider).receipt():change(self.folder,provider)
            module_payload.remove(DATA_ROOT,'notes')
        else:
            change(self.folder,self.key)
