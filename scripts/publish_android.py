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
    for old in entry['assets']:
        if old['name']==name:
            api('/releases/assets/'+str(old['id']), method='DELETE')
    url=urlsplit(entry['upload_url'].split('{')[0]+'?name='+name)
    conn=http.client.HTTPSConnection(url.hostname,timeout=600)
    with path.open('rb') as stream:
        conn.request('POST',url.path+'?'+url.query,body=stream,headers={**headers,
            'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size)})
        response=conn.getresponse(); result=json.loads(response.read())
    conn.close()
    if response.status!=201: raise RuntimeError('Upload failed: '+str(response.status))
    expected=hashlib.sha256(path.read_bytes()).hexdigest()
    if result.get('digest')!='sha256:'+expected: raise RuntimeError('Remote digest mismatch')
    print('Verified:',name,result['size'],flush=True)
body=entry.get('body') or ''
heading='### Android 手机预览版'
if heading in body: body=body.split(heading)[0].rstrip()
body+='\n\n'+heading+'\n\n下载 `'+NAME+'` 安装（Android 8+，arm64）。允许悬浮窗和屏幕采集后，回到游戏打开地图即可自动识别与叠图。支持拖动收边的状态条，长按调整难度、路线和入口校准。\n\n应用首页“检查应用更新”会先读取小体积版本清单，有新版才下载安装包，按系统提示确认覆盖安装，保留设置。首次安装仍需下载安装包；无需 Git 或电脑。预览版尚需更多真机验证。\n'
api('/releases/'+str(entry['id']), {'body':body}, 'PATCH')
published=api('/releases/'+str(entry['id']))
assert {NAME,'android-update.json'} <= {a['name'] for a in published['assets']}
assert {a['name'] for a in entry['assets'] if a['name'] not in (NAME,'android-update.json')} <= {a['name'] for a in published['assets']}
print('Published version',manifest['versionCode'],published['html_url'],flush=True)
