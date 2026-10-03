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

- **录屏设置新增画质与帧率**：画质分流畅／标准／高清，对应最长边 720／1280／1920 像素与约 2／4／8 Mbps；帧率可选 24／30／60。默认仍是原来的 1280／4 Mbps／24 帧，没改过设置的设备录出来的文件与上一版一样。设备编码器不支持所选档位时会自动降档并提示。
- **录屏默认手机声音**：录屏设置里的声音改为默认「内部声音」。以前显式点过「无声」的不受影响。需要系统录音授权（Android 10+），不采集麦克风；没授权时不提前弹窗，会在第一次录完之后提示去开启。默认值变化意味着从没设置过这一项的老用户，下次录制会开始带上游戏声音，也可能带上其他应用播放的媒体声。
- **更新改为后台下载**：点检查更新后下载在后台进行，可以离开本页面甚至切到别的应用，下完自动弹出系统安装界面。中途被系统强杀不会自动续传，下次打开会尽量接着下。
- **开图判定放宽**：原先要求两个界面控件同时高分，实测关闭按钮被挡住、或截图压缩后略掉几分时，会把确实开着的地图判成「没有地图」而不叠图。现在改成一个控件强、另一个佐证；右上角关闭图标被悬浮窗遮住时，还会用楼层按钮组独立确认。
- **沿用上次地图时更严**：本次会话已经确认过身份的地图，稀疏视野只用来重新对齐位姿，不能再用来换地图；线索不足时保留上次结果而不是改判。
- 录制时悬浮花纹持续平滑淡入淡出，可与匹配旋转叠加，停止录制后恢复。
- **辅助设置 → 轻触反馈**：控制按钮、开关及关闭操作的微震动；自动匹配结果不震动，并遵循系统触感设置。
- Android 10+ 视频保存到相册 `Movies/CrypticNotes`；Android 8/9 保存至应用外部 Movies 目录。转屏会结束当前录制。
- 支持系统提供的单应用共享选项，不再强制整屏共享。单应用共享通常不包含插件悬浮窗；录制叠图演示请选择整个屏幕。暂不支持分屏或自由窗口的坐标适配。
- 启动后台检查更新，有新版时更新栏显示红点，不自动下载。
- 改进楼层标签判定、缓存地图对齐和手机匹配筛选。探索少但特征明确的地图仍可匹配，证据不足时不强行叠图。

系统自带录屏仍可能与识图冲突。内置录屏共用原屏幕采集，默认不录制。内部声音及音画同步仍需真机验证；内部声音可能包括其他应用的媒体播放声音。识图时临时隐藏叠图的过程可能出现在视频里。

画质与帧率档位、后台下载与自动安装界面这几项**尚未在真机上验证过**。特别是「下完自动弹出安装界面」：Android 10 起从后台启动界面可能被系统静默拦下，本应用靠悬浮窗权限争取豁免，但不保证生效；被拦下时会退化成一条「更新已下载，点按完成安装」的通知，下次打开应用也会自动补装一次。安装包校验通过后才会交给系统安装器。
"""
# Android publishing only replaces Android attachments. Keep the existing
# release notes intact so Windows notes and manually edited text are preserved.
#
# The body above used to be built and then dropped on the floor -- nothing ever
# sent it -- so the Android section on the Release drifted two versions behind
# the APK it described. Publish it: everything before the Android heading is
# carried over untouched, and only the Android section is regenerated.
api('/releases/'+str(entry['id']), {'body':body}, 'PATCH')
published=api('/releases/'+str(entry['id']))
assert {NAME,'android-update.json'} <= {a['name'] for a in published['assets']}
assert {a['name'] for a in entry['assets'] if a['name'] not in (NAME,'android-update.json')} <= {a['name'] for a in published['assets']}
print('Published version',manifest['versionCode'],published['html_url'],flush=True)
