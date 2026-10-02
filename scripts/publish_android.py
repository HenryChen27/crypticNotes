"""Replace only Android assets in the existing latest Release; manifest goes last."""
import hashlib
import http.client
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / 'android/app/build/outputs/apk/debug/app-debug.apk'
NAME = 'IdentityVMapAssistant-Android-arm64.apk'
gradle = (ROOT / 'android/app/build.gradle').read_text(encoding='utf-8')
manifest = dict(packageName='com.crypticnotes.mobile',
                versionCode=int(re.search(r'versionCode\s+(\d+)', gradle)[1]),
                versionName=re.search(r"versionName\s+'([^']+)'", gradle)[1],
                asset=NAME, size=APK.stat().st_size,
                sha256=hashlib.file_digest(APK.open('rb'), 'sha256').hexdigest())
output = ROOT / 'out/android-update.json'
output.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
credential = subprocess.run(['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True, check=True)
fields = dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
headers = {'Authorization':'Bearer '+fields['password'], 'User-Agent':'crypticNotes',
           'Accept':'application/vnd.github+json'}
base = 'https://api.github.com/repos/HenryChen27/crypticNotes'
def api(path, data=None, method=None):
    req = urllib.request.Request(base+path, headers=headers,
        data=json.dumps(data).encode() if data is not None else None, method=method)
    with urllib.request.urlopen(req,timeout=60) as response:
        raw=response.read()
        return json.loads(raw) if raw else None

entry = api('/releases/latest')
print('Updating existing release:', entry['html_url'], flush=True)
for name, path in [(NAME, APK), ('android-update.json', output)]:
    temporary=name+'.pending-'+str(manifest['versionCode'])
    url=urlsplit(entry['upload_url'].split('{')[0]+'?name='+temporary)
    conn=http.client.HTTPSConnection(url.hostname,timeout=600)
    with path.open('rb') as stream:
        conn.request('POST',url.path+'?'+url.query,body=stream,headers={**headers,
            'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size)})
        response=conn.getresponse(); result=json.loads(response.read())
    conn.close()
    if response.status!=201: raise RuntimeError('Upload failed: '+str(response.status))
    expected=hashlib.sha256(path.read_bytes()).hexdigest()
    if result.get('digest')!='sha256:'+expected: raise RuntimeError('Remote digest mismatch')
    for old in entry['assets']:
        if old['name']==name:
            api('/releases/assets/'+str(old['id']), method='DELETE')
    api('/releases/assets/'+str(result['id']), {'name':name}, 'PATCH')
    print('Verified:',name,result['size'],flush=True)
body=entry.get('body') or ''
heading='### Android 手机预览版'
if heading in body: body=body.split(heading)[0].rstrip()
body += f"""

{heading}

当前版本：**{manifest['versionName']}**（Android 8+，arm64）。下载 `{NAME}`，已有安装可在应用内检查更新，覆盖安装保留设置。

- **录屏设置移至 App 内**：声音可选择无声或内部声音，悬浮窗只保留开始／停止录制。Android 10+ 内部声音需要系统录音授权，不采集麦克风；游戏禁止第三方采集时可能仍无声。
- 录制时悬浮花纹持续平滑淡入淡出，可与匹配旋转叠加，停止录制后恢复。
- **辅助设置 → 轻触反馈**：控制按钮、开关及关闭操作的微震动；自动匹配结果不震动，并遵循系统触感设置。
- Android 10+ 视频保存到相册 `Movies/CrypticNotes`；Android 8/9 保存至应用外部 Movies 目录。最长边 1280、最高 24 帧，转屏会结束当前录制。实际性能和兼容性仍待更多真机测试。
- 支持系统提供的单应用共享选项，不再强制整屏共享。单应用共享通常不包含插件悬浮窗；录制叠图演示请选择整个屏幕。暂不支持分屏或自由窗口的坐标适配。
- 启动后台检查更新，有新版时更新栏显示红点，不自动下载。
- 改进楼层标签判定、缓存地图对齐和手机匹配筛选。探索少但特征明确的地图仍可匹配，证据不足时不强行叠图。

系统自带录屏仍可能与识图冲突。内置录屏共用原屏幕采集，默认不录制、默认无声。内部声音及音画同步仍需真机验证；内部声音可能包括其他应用的媒体播放声音。识图时临时隐藏叠图的过程可能出现在视频里。画质为最长边 1280、最高 24 帧、4 Mbps，不跟随系统录屏设置。
"""
# Android publishing only replaces Android attachments. Keep the existing
# release notes intact so Windows notes and manually edited text are preserved.
published=api('/releases/'+str(entry['id']))
assert {NAME,'android-update.json'} <= {a['name'] for a in published['assets']}
assert {a['name'] for a in entry['assets'] if a['name'] not in (NAME,'android-update.json')} <= {a['name'] for a in published['assets']}
print('Published version',manifest['versionCode'],published['html_url'],flush=True)
