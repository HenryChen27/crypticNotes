"""Replace Windows assets in the existing latest release, preserving Android."""
import hashlib
import http.client
import json
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
names = ['IdentityVMapAssistant-Windows-x64.zip', 'SHA256SUMS.txt', 'windows-update.json']
manifest = json.loads((ROOT/'release/windows-update.json').read_text())
assert hashlib.sha256((ROOT/'release'/names[0]).read_bytes()).hexdigest() == manifest['sha256']
credential = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, check=True)
fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
headers = {'Authorization': 'Bearer '+fields['password'], 'User-Agent': 'crypticNotes',
           'Accept': 'application/vnd.github+json'}
base = 'https://api.github.com/repos/HenryChen27/crypticNotes'

def api(path, data=None, method=None):
    req = urllib.request.Request(base+path, headers=headers, method=method,
                                 data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else None

entry = api('/releases/latest')
print('Updating existing release:', entry['html_url'], flush=True)
uploaded = []
for name in names:
    path = ROOT/'release'/name
    temporary = name+'.pending-'+str(manifest['build'])
    url = urlsplit(entry['upload_url'].split('{')[0]+'?name='+temporary)
    conn = http.client.HTTPSConnection(url.hostname, timeout=600)
    with path.open('rb') as stream:
        conn.request('POST', url.path+'?'+url.query, body=stream, headers={**headers,
                     'Content-Type': 'application/octet-stream', 'Content-Length': str(path.stat().st_size)})
        response = conn.getresponse()
        result = json.loads(response.read())
    conn.close()
    if response.status != 201:
        raise RuntimeError('Upload failed: '+str(response.status))
    digest = 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.get('digest') == digest, 'Remote digest mismatch'
    uploaded.append((name, result['id'], digest))
    print('Uploaded and verified:', name, flush=True)

# Download all replacements successfully before touching any existing attachment.
# Publish the small version manifest last so mixed versions fail closed.
for name, asset_id, digest in uploaded:
    for old in entry['assets']:
        if old['name'] == name:
            api('/releases/assets/'+str(old['id']), method='DELETE')
    api('/releases/assets/'+str(asset_id), {'name': name}, 'PATCH')

old_body = entry.get('body') or ''
heading = '### Android 手机预览版'
android = '\n\n'+heading+old_body.split(heading, 1)[1] if heading in old_body else ''
body = '''《第五人格》加页手记地图助手。根据屏幕截图识别地图与楼层，把完整地图和参考路线半透明叠在游戏画面上，帮助探索与找路。支持困难、噩梦单人及多人路线；单人和多人选项用于选择参考路线。

### Windows 便携版

下载 `IdentityVMapAssistant-Windows-x64.zip`，完整解压后双击 `crypticNotes.cmd`。无需安装 Python 或 Git。设置与游戏一致的地图快捷键，打开游戏地图即可识别；支持透明度调整、地图管理、手动录入和本地截图测试。

在「使用偏好」点击「检查更新」，或双击 `更新.cmd`，即可检查版本、下载校验、自动替换并重启。需要能够访问 GitHub；更新采用完整包下载，保留设置、识别记录和整个本地地图库，不自动覆盖自录地图或同步新版内置地图。旧版仍要求 Git 的用户，请先下载此包迁移一次。

首次使用默认展开等待为 150 毫秒，已有自定义值保留。开图后请稍作停留，立即关闭仍可能来不及识别。可使用布偶外观和对话提示，关闭个性外观即可恢复齿轮。运行 `create-shortcut.cmd` 可以生成桌面快捷方式。

截图在本地处理，不读取或修改游戏内存。可选记录成功与失败案例，每类保留最近 20 条；分享记录前请检查私人信息。地图与路线素材来自凉哈皮。详细说明见仓库 README。'''
# Windows publishing only replaces the Windows attachments. Keep the existing
# release notes intact so Android notes and manually edited text are preserved.
published = api('/releases/'+str(entry['id']))
for name, asset_id, digest in uploaded:
    asset = next(a for a in published['assets'] if a['name'] == name)
    assert asset['id'] == asset_id and asset['digest'] == digest
for old in entry['assets']:
    if old['name'] not in names:
        assert any(a['id'] == old['id'] for a in published['assets'])
print('Published and verified:', published['html_url'], flush=True)
