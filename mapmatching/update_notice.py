"""Read-only startup version probe; never downloads an update package."""
import json
from urllib.request import Request, urlopen


def read_json(url):
    if not url.startswith('https://'):
        raise ValueError('HTTPS required')
    with urlopen(Request(url, headers={'User-Agent':'CrypticNotes-Windows'}), timeout=12) as response:
        data=response.read(2_000_001)
    if len(data)>2_000_000:
        raise ValueError('Update metadata too large')
    return json.loads(data)


def newer_build(root, fetch=read_json):
    stamp=root/'windows-build.json'
    if not stamp.is_file():
        return False
    local=json.loads(stamp.read_text(encoding='utf-8-sig'))
    release=fetch('https://api.github.com/repos/HenryChen27/crypticNotes/releases/latest')
    assets={a['name']:a for a in release['assets']}
    manifest=fetch(assets['windows-update.json']['browser_download_url'])
    package=assets['IdentityVMapAssistant-Windows-x64.zip']
    return (int(manifest['build'])>int(local['build'])
            and int(manifest['size'])==int(package['size'])
            and package.get('digest','').lower()=='sha256:'+manifest['sha256'].lower())


def watch_once(parent, root, callback):
    import queue
    import threading
    from PySide6 import QtCore as C
    result=queue.Queue()
    def probe():
        try:
            result.put(newer_build(root))
        except Exception:
            result.put(None)  # Offline is not "up to date"; leave UI untouched.
    timer=C.QTimer(parent)
    def poll():
        try:
            available=result.get_nowait()
        except queue.Empty:
            return
        timer.stop()
        if available is not None:
            callback(available)
        timer.deleteLater()
    timer.timeout.connect(poll)
    timer.start(200)
    threading.Thread(target=probe,name='update-notice',daemon=True).start()
