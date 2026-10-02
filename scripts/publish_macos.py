"""Replace macOS assets in the existing latest release, preserving everything else.

Mirrors publish_windows.py: upload under a temporary name, verify the digest
GitHub computed, and only then delete the old attachment and rename the new one.
A failure at any point leaves the previous downloads untouched.
"""
import hashlib
import http.client
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ARCHES = ('arm64', 'x64')
SUMS = 'macos-{arch}-SHA256SUMS.txt'


def assets_for(arch):
    return [f'IdentityVMapAssistant-macOS-{arch}.zip', SUMS.format(arch=arch)]


def digest_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_digest(arch):
    text = (ROOT/'release'/SUMS.format(arch=arch)).read_text(encoding='utf-8')
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == f'IdentityVMapAssistant-macOS-{arch}.zip':
            return fields[0].lower()
    raise SystemExit(f'{SUMS.format(arch=arch)} 里没有对应条目')


def main():
    wanted = [arch for arch in ARCHES if (ROOT/'release'/f'IdentityVMapAssistant-macOS-{arch}.zip').exists()]
    if not wanted:
        raise SystemExit('release/ 里没有 macOS 包，先跑 scripts/build_macos.py')
    names = [name for arch in wanted for name in assets_for(arch)]
    for arch in wanted:
        digest = digest_of(ROOT/'release'/f'IdentityVMapAssistant-macOS-{arch}.zip')
        assert digest == expected_digest(arch), f'{arch} 的 zip 与 SHA256SUMS 不一致'
        print(f'  {arch}: sha256 与 {SUMS.format(arch=arch)} 一致', flush=True)

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
        temporary = name+'.pending-macos'
        url = urlsplit(entry['upload_url'].split('{')[0]+'?name='+temporary)
        conn = http.client.HTTPSConnection(url.hostname, timeout=1800)
        with path.open('rb') as stream:
            conn.request('POST', url.path+'?'+url.query, body=stream, headers={**headers,
                         'Content-Type': 'application/octet-stream', 'Content-Length': str(path.stat().st_size)})
            response = conn.getresponse()
            result = json.loads(response.read())
        conn.close()
        if response.status != 201:
            raise RuntimeError('Upload failed: '+str(response.status)+' '+str(result))
        digest = 'sha256:'+digest_of(path)
        assert result.get('digest') == digest, 'Remote digest mismatch for '+name
        uploaded.append((name, result['id'], digest))
        print('Uploaded and verified:', name, flush=True)

    # Everything is on the server before any existing attachment is removed.
    for name, asset_id, digest in uploaded:
        for old in entry['assets']:
            if old['name'] == name:
                api('/releases/assets/'+str(old['id']), method='DELETE')
        api('/releases/assets/'+str(asset_id), {'name': name}, 'PATCH')

    published = api('/releases/'+str(entry['id']))
    for name, asset_id, digest in uploaded:
        asset = next(a for a in published['assets'] if a['name'] == name)
        assert asset['id'] == asset_id and asset['digest'] == digest, 'Verification failed for '+name
    for old in entry['assets']:
        if old['name'] not in names:
            assert any(a['id'] == old['id'] for a in published['assets']), old['name']+' disappeared'
    print('Published and verified:', published['html_url'], flush=True)
    print('Release body untouched:', published.get('body') == entry.get('body'), flush=True)


if __name__ == '__main__':
    sys.exit(main())
