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
body+=('\n\n'+heading+'\n\n'
 '下载 `'+NAME+'` 安装（Android 8+，arm64）。允许悬浮窗和屏幕采集后，回到游戏打开地图即可自动识别与叠图。\n\n'
 '游戏内的小圆钮**一直显示**，可以拖到任意位置，建议留在屏幕左侧。空闲时只显示纹章；识别中纹章持续旋转（不再用文字遮挡地图）；出结果时纹章旁边像对话框一样冒出一条短提示，约 1.8 秒后自动收回，拖动时立刻收起。**单击开关游戏设置、双击立刻重新识别、长按关闭识别**（小圆钮同时消失）。双击会撤掉旧叠图并马上重跑一次检测，不用再干等下一轮；它不绕过地图展开验证，地图没展开时仍然不匹配。因为要区分单双击，单击设置会比平时晚约 0.3 秒生效。长按的判定时间放宽到 0.9 秒（比系统默认的 0.5 秒长），这是四个手势里唯一会关掉识别的，宁可按住久一点，也别误触。\n\n'
 '游戏设置面板整体缩小：横屏下不用滑动就能看到全部按钮，标题不再贴着顶边，右上角是一个独立的叉。面板内难度与参考路线**改动即生效**（后台重建匹配器约 1 秒），并显示当前生效的组合；新增「隐藏叠图」，可临时把叠图收起来。\n\n'
 '首页的「游戏设置」折叠栏点标题展开／收起，样式与应用更新一致，**默认展开**；悬浮球尺寸与叠图不透明度的改动**立即生效**，不必重启。检查应用更新时不再有进度条，改为旋转的纹章。\n\n'
 '**修复**：上一版首页的「游戏设置」整栏不见了。原因是折叠栏的标题从来没被加进界面（漏了一行 `addView`），内容又默认收起，于是整栏凭空消失——编译、检查、运行都不报错，难度/尺寸/地图管理等设置因此在首页完全点不到。现在折叠栏的标题与内容由同一个方法一次建成，并加了源码级检查防止再漏。\n\n'
 '应用首页“检查应用更新”会先读取小体积版本清单，有新版才下载安装包，按系统提示确认覆盖安装，保留设置。首次安装仍需下载安装包；无需 Git 或电脑。预览版尚需更多真机验证。\n')
api('/releases/'+str(entry['id']), {'body':body}, 'PATCH')
published=api('/releases/'+str(entry['id']))
assert {NAME,'android-update.json'} <= {a['name'] for a in published['assets']}
assert {a['name'] for a in entry['assets'] if a['name'] not in (NAME,'android-update.json')} <= {a['name'] for a in published['assets']}
print('Published version',manifest['versionCode'],published['html_url'],flush=True)
