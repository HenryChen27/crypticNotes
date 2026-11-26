"""Public update discovery. Credentials are never required on user devices."""
import copy,json,re
from urllib.parse import urlsplit,unquote
from urllib.request import Request,urlopen
PRIMARY_RELEASE='https://api.gitcode.com/api/v5/repos/weixin_51917701/crypticNotes/releases/latest'
FALLBACK_RELEASE='https://api.github.com/repos/HenryChen27/crypticNotes/releases/latest'
PREFIXES=('https://gitcode.com/weixin_51917701/crypticNotes/releases/download/',
          'https://github.com/HenryChen27/crypticNotes/releases/download/')

def official_download(url):
    if not isinstance(url,str) or not url.startswith(PREFIXES):return False
    path=unquote(urlsplit(url).path).replace('\\','/')
    return not any(part in ('.','..') for part in path.split('/'))

def read_json(url):
    if not url.startswith('https://'):raise ValueError('HTTPS required')
    with urlopen(Request(url,headers={'User-Agent':'CrypticNotes-update','Cache-Control':'no-cache'}),timeout=15) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('Update metadata too large')
    return json.loads(raw)

def load_release(fetch=read_json,required=(),verified=False):
    missing=[]
    for url in (PRIMARY_RELEASE,FALLBACK_RELEASE):
        try:
            release=fetch(url)
            if not isinstance(release.get('assets'),list):raise ValueError('Invalid release metadata')
            for name in required:
                asset=release_asset(release,name)
                if verified and (not re.fullmatch('sha256:[a-f0-9]{64}',asset.get('digest') or '') or not isinstance(asset.get('size'),int) or asset['size']<=0):
                    raise ValueError('附件缺少完整校验信息：'+name)
            return release
        except Exception as error:missing.append(str(error))
    raise ValueError('未能取得正式发布附件：'+'；'.join(dict.fromkeys(missing)))

def release_asset(release,name):
    matches=[a for a in release['assets'] if a.get('name')==name]
    if not matches:raise ValueError('尚未上架：'+name)
    if len(matches)!=1 or not official_download(matches[0].get('browser_download_url')):
        raise ValueError('附件地址或数量不正确：'+name)
    return matches[0]

def module_info(key):
    from .paths import ROOT,FROZEN
    from .module_payload import ASSETS,digest
    name=ASSETS[key]
    local=ROOT/'release'/name
    if not FROZEN and local.is_file():
        return dict(asset=name,size=local.stat().st_size,sha256=digest(local),url=local.as_uri())
    reviewed=review_info(key,name)
    if reviewed:return reviewed
    asset=release_asset(load_release(required=(name,),verified=True),name)
    return dict(asset=name,size=asset['size'],sha256=asset['digest'][7:],url=asset['browser_download_url'])

def review_info(key,name):
    from .paths import ROOT,FROZEN
    from pathlib import Path
    import os,sys
    pins=ROOT/'module-review.json'
    if not FROZEN or not pins.is_file():return None
    spec=json.loads(pins.read_text(encoding='utf8')).get(key)
    if not spec or name!=spec.get('asset'):return None
    directory=Path(sys.executable).parent
    candidates=[directory/'review-packages',directory.parent/'review-packages']
    if os.environ.get('JYSJ_REVIEW_PACKAGES'):candidates.insert(0,Path(os.environ['JYSJ_REVIEW_PACKAGES']))
    for folder in candidates:
        path=folder/name
        if path.is_file():return dict(spec,url=path.resolve().as_uri())
    return None

def load_map_catalog(fetch=read_json):
    release=load_release(fetch)
    catalog=copy.deepcopy(fetch(release_asset(release,'matching-module.json')['browser_download_url']))
    for spec in [catalog,*catalog.get('providers',{}).values()]:
        asset=release_asset(release,spec['asset'])
        if asset.get('size')!=spec['size'] or asset.get('digest','').lower()!='sha256:'+spec['sha256'].lower():
            raise ValueError('地图库发布文件正在更新，请稍后重试')
        spec['url']=asset['browser_download_url']
    return catalog
