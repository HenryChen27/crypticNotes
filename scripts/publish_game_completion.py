"""Complete the reviewed 2.4.0 draft, checking every public asset."""
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit, quote
import release_manager as r

r.REPO = 'HenryChen27/Jellyfish'
g = r.GitHub()
release = next(x for x in g.api('/releases?per_page=30') if x['tag_name']=='desktop-v2.4.0')
assert release['draft'], 'Expected the reviewed draft'
folder = r.ROOT / 'out/minigames-native'
local = json.loads((folder/'native-desktop-games.json').read_text())
asset = next(a for a in release['assets'] if a['name']=='native-desktop-games.json')
g.headers['Accept']='application/octet-stream'
previous = json.loads(g.download(asset['url']))
g.headers['Accept']='application/vnd.github+json'
assert previous['game']['sha256']==local['game']['sha256'], 'Game resources differ from reviewed draft'
previous['launchers']['windows-x64']=local['launchers']['windows-x64']
for key, info in previous['launchers'].items():
    if key=='windows-x64': continue
    name=info['url'].rsplit('/',1)[1]
    existing=next(a for a in release['assets'] if a['name']==name)
    assert existing['digest']=='sha256:'+info['sha256'] and existing['size']==info['size']
(folder/'native-desktop-games.json').write_text(json.dumps(previous,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ('GameLauncher-windows-x64.zip','native-desktop-games.json'):
    path=folder/name
    expected=r.digest(path)
    pending=name+'.pending-'+expected[:12]
    url=urlsplit(release['upload_url'].split('{')[0]+'?name='+quote(pending))
    conn=http.client.HTTPSConnection(url.hostname,timeout=900)
    with path.open('rb') as stream:
        conn.request('POST',url.path+'?'+url.query,body=stream,headers={**g.headers,'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size)})
        response=conn.getresponse(); result=json.loads(response.read())
    conn.close()
    assert response.status==201 and result['digest']=='sha256:'+expected, result
    for old in g.api('/releases/'+str(release['id']))['assets']:
        if old['name']==name:g.api('/releases/assets/'+str(old['id']),method='DELETE')
    g.api('/releases/assets/'+str(result['id']),{'name':name},'PATCH')
    print('Verified:',name,flush=True)
result=g.api('/releases/'+str(release['id']),{'draft':False,'prerelease':False,'make_latest':'true','name':'合成大水母 2.4.0 · 可选小游戏','body':'可选下载的完整小游戏资源与共用系统网页引擎启动器。更新无边框窗口控制、静音、最小化及恢复、蓝水母图标与安全保存退出。Windows 配合最新版插件支持画面大幅变化后收起，5 秒内未恢复则安全保存关闭。手机使用最新版插件内置的悬浮启动器。小游戏资源与存档分开管理。'},'PATCH')
assert g.api('/releases/latest')['id']==release['id']
remote=g.manifest(result,'native-desktop-games.json')
assert remote==previous
for info in [remote['game'],*remote['launchers'].values()]:
    assert any(a['name']==info['url'].rsplit('/',1)[1] and a['digest']=='sha256:'+info['sha256'] for a in result['assets'])
print('Published and verified:',result['html_url'])
