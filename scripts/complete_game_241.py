"""Collect verified Mac launchers, then publish the reviewed game release."""
import io
import json
import time
import zipfile
import urllib.error
import release_manager as r

g=r.GitHub()
before=json.loads((r.ROOT/'out/game-build-dispatch.json').read_text())['before']
path='/actions/workflows/native-games.yml/runs?per_page=10'
deadline=time.monotonic()+3600
while time.monotonic()<deadline:
    run=next((x for x in g.api(path)['workflow_runs'] if x['id'] not in before and x['event']=='workflow_dispatch'),None)
    if run:
        print(run['html_url'],run['status'],flush=True)
        if run['status']=='completed':
            assert run['conclusion']=='success',run['html_url']
            break
    time.sleep(20)
else:raise RuntimeError('Game workflow timeout')
folder=r.ROOT/'out/minigames-native'
catalog=json.loads((folder/'native-desktop-games.json').read_text())
for artifact in g.api('/actions/runs/'+str(run['id'])+'/artifacts')['artifacts']:
    if not artifact['name'].startswith('NativeGames-macos-'):continue
    with zipfile.ZipFile(io.BytesIO(g.download(artifact['archive_download_url']))) as z:
        other=json.loads(z.read('native-desktop-games.json'))
        with zipfile.ZipFile(io.BytesIO(z.read('Jellyfish-game.zip'))) as remote_game, zipfile.ZipFile(folder/'Jellyfish-game.zip') as local_game:
            assert set(remote_game.namelist())==set(local_game.namelist()),'Remote game file set differs from local'
            for name in local_game.namelist():
                remote_bytes=remote_game.read(name); local_bytes=local_game.read(name)
                if name.endswith(('.js','.css','.html','.txt')):
                    remote_bytes=remote_bytes.replace(b'\r\n',b'\n');local_bytes=local_bytes.replace(b'\r\n',b'\n')
                assert remote_bytes==local_bytes,'Remote game content differs: '+name
        for key,info in other['launchers'].items():
            name=info['url'].rsplit('/',1)[1]
            (folder/name).write_bytes(z.read(name))
            assert r.digest(folder/name)==info['sha256']
            catalog['launchers'][key]=info
assert set(catalog['launchers'])=={'windows-x64','macos-arm64','macos-x64'}
(folder/'native-desktop-games.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
r.REPO='HenryChen27/Jellyfish'
latest=g.api('/releases/latest')
legacy=next(a for a in latest['assets'] if a['name']=='desktop-games.json')
(folder/'desktop-games.json').write_bytes(g.download(legacy['browser_download_url']))
release=g.api('/releases',{'tag_name':'desktop-v2.4.1','name':'合成大水母 2.4.1 · 本机功能同步','target_commitish':'main','body':'修正启动器版本复用导致旧界面未更新的问题。新版无边框按钮、静音与最小化恢复、安全保存退出。Windows 配合最新插件检测游戏画面变化，收起后 5 秒内未恢复则安全保存关闭。手机在新版插件的小游戏栏下载资源，以悬浮窗口运行。','draft':False,'make_latest':'true'},'POST')
files={name:r.digest(folder/name) for name in ['Jellyfish-game.zip','native-desktop-games.json','desktop-games.json',*[info['url'].rsplit('/',1)[1] for info in catalog['launchers'].values()]]}
r.publish(g,{'id':'game241','release_id':release['id'],'files':files},folder)
assert g.manifest(g.api('/releases/latest'),'native-desktop-games.json')==catalog
print('Verified complete 2.4.1 game release',flush=True)
