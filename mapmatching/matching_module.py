"""Optional matching library; uninstall retains user data without destructive guesses."""
import json,shutil,urllib.request,hashlib,zipfile,uuid
from pathlib import Path,PurePosixPath
from .paths import ROOT,DATA_ROOT,FROZEN

MANIFEST='https://github.com/HenryChen27/crypticNotes/releases/latest/download/matching-module.json'
class MatchingModule:
    def __init__(self,provider=None):
        self.provider=provider
        if provider not in (None,'lianghapi','zhanshi'):raise ValueError('Unknown map provider')
        self.latest=None
        self.folder=DATA_ROOT/'modules/mapmatching'
        self.state=DATA_ROOT/'modules/matching-state.json'
    def enabled(self):
        try:state=json.loads(self.state.read_text(encoding='utf8'))
        except (OSError,ValueError):state={}
        if not state.get('enabled',True):return False
        if self.provider is None:
            path=self.root()/'maps/floors.json'
            try:
                manifest=json.loads(path.read_text(encoding='utf8'))
                return bool(manifest.get('references')) or manifest.get('schema_version')!=2
            except (OSError,ValueError):return False
        from .src.provider_packages import installed
        providers=[self.provider] if self.provider else ['lianghapi','zhanshi']
        return any(state.get('providers',{}).get(p,True) and installed(self.root()/'maps',p) for p in providers)
    def author_enabled(self,provider):return MatchingModule(provider).enabled()
    def set_author_enabled(self,value):
        try:state=json.loads(self.state.read_text(encoding='utf8'))
        except (OSError,ValueError):state={}
        state.setdefault('providers',{})[self.provider]=bool(value)
        if value:state['enabled']=True
        self.state.parent.mkdir(parents=True,exist_ok=True)
        temp=self.state.with_suffix('.tmp');temp.write_text(json.dumps(state),encoding='utf8');temp.replace(self.state)
    def choose(self,catalog):
        provider=self.provider or 'lianghapi'
        if 'providers' in catalog:
            if provider not in catalog['providers']:raise ValueError('此版本尚未提供该作者地图库')
            spec=catalog['providers'][provider]
            if spec.get('provider')!=provider:raise ValueError('地图库作者清单不一致')
        elif provider=='lianghapi':spec=catalog
        else:raise ValueError('请等待展十地图库发布后重试')
        self.latest=spec
        return spec
    def root(self):
        if not FROZEN and (ROOT/'maps/floors.json').is_file():return ROOT
        return self.folder if (self.folder/'maps/floors.json').is_file() else ROOT
    def set_enabled(self,value):
        try:state=json.loads(self.state.read_text(encoding='utf8'))
        except (OSError,ValueError):state={}
        state['enabled']=bool(value);self.state.parent.mkdir(parents=True,exist_ok=True)
        temp=self.state.with_suffix('.tmp');temp.write_text(json.dumps(state),encoding='utf8');temp.replace(self.state)
    def version(self):
        if not self.enabled():return '未安装'
        try:
            receipt=self.root()/'maps/packages'/f'{self.provider}.json' if self.provider else self.folder/'module.json'
            spec=json.loads(receipt.read_text(encoding='utf-8'))
            return str(spec.get('version') or ('库-'+spec['sha256'][:12]))
        except (OSError,ValueError,KeyError):
            try:return '清单-'+hashlib.sha256((self.root()/'maps/floors.json').read_bytes()).hexdigest()[:12]
            except OSError:return '未读取'

    def update_available(self):
        local=ROOT/'release/matching-module.json'
        if not FROZEN and local.is_file():spec=json.loads(local.read_text(encoding='utf-8'))
        else:
            request=urllib.request.Request(MANIFEST,headers={'User-Agent':'CrypticNotes-modules'})
            with urllib.request.urlopen(request,timeout=30) as response:raw=response.read(32769)
            if len(raw)>32768:raise ValueError('地图模块清单过大')
            spec=json.loads(raw)
        spec=self.choose(spec)
        if not isinstance(spec.get('sha256'),str) or len(spec['sha256'])!=64:raise ValueError('无效模块校验值')
        current=self.root()/'maps/packages'/f'{self.provider}.json' if self.provider else self.folder/'module.json'
        if not current.is_file():return self.root()!=ROOT or FROZEN
        return json.loads(current.read_text(encoding='utf-8')).get('sha256')!=spec['sha256']

    def download(self,progress,cancelled=lambda:False):
        local=ROOT/'release/matching-module.json'
        local_archive=ROOT/'release/IdentityVMapAssistant-Matching.zip'
        if not FROZEN and local.is_file():
            selected=self.choose(json.loads(local.read_text(encoding='utf8')))
            local_archive=ROOT/'release'/selected['asset']
        development=not FROZEN and local.is_file() and local_archive.is_file()
        if development:
            raw=local.read_bytes();progress(0,'正在安装本地测试模块…')
        else:
            request=urllib.request.Request(MANIFEST,headers={'User-Agent':'CrypticNotes-modules'})
            with urllib.request.urlopen(request,timeout=30) as response:raw=response.read(32769)
        if len(raw)>32768:raise ValueError('地图模块清单过大')
        spec=self.choose(json.loads(raw));url=spec['url'];sha=spec['sha256'];size=spec['size']
        if not url.startswith('https://github.com/HenryChen27/crypticNotes/releases/download/') or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or not isinstance(size,int) or not 0<size<600*1024**2:
            raise ValueError('地图模块下载信息无效')
        parent=self.folder.parent;parent.mkdir(parents=True,exist_ok=True)
        stage=parent/('.matching-'+uuid.uuid4().hex);stage.mkdir();archive=stage/'module.zip'
        try:
            digest=hashlib.sha256();count=0
            download_url=local_archive.resolve().as_uri() if development else url
            with urllib.request.urlopen(urllib.request.Request(download_url,headers={'User-Agent':'CrypticNotes-modules'}),timeout=45) as src,archive.open('wb') as dst:
                while block:=src.read(256*1024):
                    if cancelled():raise InterruptedError('已取消下载')
                    count+=len(block)
                    if count>size:raise ValueError('模块大小异常')
                    dst.write(block);digest.update(block);progress(count*85//size,'正在下载加页手记…')
            if count!=size or digest.hexdigest()!=sha:raise ValueError('模块校验失败')
            payload=stage/'payload';payload.mkdir();seen=set();total=0
            with zipfile.ZipFile(archive) as z:
                for item in z.infolist():
                    name=item.filename.replace('\\','/');target=payload/name
                    if not name.startswith('maps/') or '..' in PurePosixPath(name).parts or not target.resolve().is_relative_to((payload/'maps').resolve()) or ':' in name or name.casefold() in seen or ((item.external_attr>>16)&0o170000)==0o120000:raise ValueError('无效模块路径')
                    seen.add(name);total+=item.file_size
                    if total>1400*1024**2 or len(seen)>20000:raise ValueError('模块解压大小异常')
                    if item.is_dir():target.mkdir(parents=True,exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        with z.open(item) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
            if not (payload/'maps/floors.json').is_file():raise ValueError('模块缺少地图清单')
            if self.provider:
                from .src.provider_packages import change
                if not (self.folder/'maps').exists():
                    retained=DATA_ROOT/'module-user-data/mapmatching/maps'
                    legacy=retained if retained.exists() else ROOT/'maps'
                    if FROZEN and legacy.is_dir():shutil.copytree(legacy,self.folder/'maps')
                change(self.folder,self.provider,payload/'maps',spec)
                self.set_author_enabled(True);progress(100,'地图库已安装');return
            from .src.map_update import merge
            old=self.folder/'maps'
            retained=DATA_ROOT/'module-user-data/mapmatching/maps'
            if not old.exists():old=retained if retained.exists() else ROOT/'maps'
            merge(old,payload/'maps')
            backup=self.folder.with_name('.mapmatching-previous')
            if backup.exists():shutil.rmtree(backup)
            if self.folder.exists():self.folder.rename(backup)
            try:payload.rename(self.folder)
            except BaseException:
                if backup.exists():backup.rename(self.folder)
                raise
            if backup.exists():shutil.rmtree(backup)
            (self.folder/'module.json').write_text(json.dumps(spec),encoding='utf-8')
            self.set_enabled(True);progress(100,'加页手记已安装')
        finally:shutil.rmtree(stage,ignore_errors=True)
    def delete(self):
        if self.provider:
            from .src.provider_packages import change
            root=self.root()
            if FROZEN or root!=ROOT:change(root,self.provider)
            self.set_author_enabled(False);return
        from .src.map_update import merge
        old=self.root()/'maps'
        retained=DATA_ROOT/'module-user-data/mapmatching/maps'
        stage=retained.with_name('.preserve-'+uuid.uuid4().hex);stage.mkdir(parents=True)
        try:
            for name,value in [('floors.json',{'references':[]}),('disabled.json',{'records':[]})]:
                (stage/name).write_text(json.dumps(value),encoding='utf-8')
            # Provenance separates official payload from personal maps. Unknown legacy
            # files are retained rather than guessed; source checkout is never removed.
            merge(old,stage)
            if retained.exists():shutil.rmtree(retained)
            stage.rename(retained)
            self.set_enabled(False)
            if self.folder.exists():shutil.rmtree(self.folder)
            if FROZEN and old==ROOT/'maps' and old.exists():shutil.rmtree(old)
        finally:
            if stage.exists():shutil.rmtree(stage)
