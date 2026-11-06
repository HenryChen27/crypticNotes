"""Verify final release digests and document this specific correction."""
import json
import time
import release_manager as r

folder=r.ROOT/'release/jobs/20261012-232427'
state=json.loads((folder/'release-job.json').read_text(encoding='utf-8'))
g=r.GitHub()
for attempt in range(60):
    release=g.api('/releases/latest?v='+str(time.time_ns()))
    assets={a['name']:a.get('digest') for a in release['assets']}
    if all(assets.get(n)=='sha256:'+sha for n,sha in state['files'].items()):break
    time.sleep(10)
else:raise RuntimeError('Final release verification timeout')
android=g.manifest(release,'android-update.json')
assert android['versionCode']==30 and android['packageName']=='com.crypticnotes.mobile.v2'
note='<!-- correction-20261012-232427 -->\n### 本机功能同步与更新修复\n\n- Android 0.6.22-preview（30）：应用名称增加“新版”，显示当前版本，展开小游戏入口；包含小游戏悬浮窗口与跨楼层强行叠图。旧签名应用请手动安装此 APK，新旧应用可共存。\n- Windows：同步本机窗口采集、强行叠图、小游戏后台检测与 5 秒安全退出逻辑。\n- macOS 1.0.10：同步当前源码并通过两种架构的构建与启动检查。\n- 小游戏及共用启动器升级至 2.4.1。在小游戏栏点击更新游戏，避免沿用旧启动器；新版客户端同版本也校验下载身份。游戏存档保留。\n\n'
body=release.get('body') or ''
if '<!-- correction-20261012-232427 -->' not in body:
    g.api('/releases/'+str(release['id']),{'name':'加页手记 · 2026-10-12 三端最新版','body':note+body},'PATCH')
r.REPO='HenryChen27/Jellyfish'
game=g.api('/releases/latest')
assert game['tag_name']=='desktop-v2.4.1'
catalog=g.manifest(game,'native-desktop-games.json')
for info in [catalog['game'],*catalog['launchers'].values()]:
    assert info['version']=='2.4.1'
    assert any(a['name']==info['url'].rsplit('/',1)[1] and a['digest']=='sha256:'+info['sha256'] for a in game['assets'])
report={'plugin':release['html_url'],'game':game['html_url'],'android':android,'plugin_files':state['files'],'game_catalog':catalog,'verified':True}
(folder/'remote-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('ALL final remote assets and manifests verified',flush=True)
