"""Public update discovery. Credentials are never required on user devices."""
import copy,json
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

def load_release(fetch=read_json):
    for url in (PRIMARY_RELEASE,FALLBACK_RELEASE):
        try:
            release=fetch(url)
            if not isinstance(release.get('assets'),list):raise ValueError('Invalid release metadata')
            return release
        except Exception:
            if url==FALLBACK_RELEASE:raise

def release_asset(release,name):
    matches=[a for a in release['assets'] if a.get('name')==name]
    if len(matches)!=1 or not official_download(matches[0].get('browser_download_url')):
        raise ValueError('发布附件缺失或地址无效：'+name)
    return matches[0]

def load_map_catalog(fetch=read_json):
    release=load_release(fetch)
    catalog=copy.deepcopy(fetch(release_asset(release,'matching-module.json')['browser_download_url']))
    for spec in [catalog,*catalog.get('providers',{}).values()]:
        asset=release_asset(release,spec['asset'])
        if asset.get('size')!=spec['size'] or asset.get('digest','').lower()!='sha256:'+spec['sha256'].lower():
            raise ValueError('地图库发布文件正在更新，请稍后重试')
        spec['url']=asset['browser_download_url']
    return catalog
