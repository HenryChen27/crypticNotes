"""Exercise the downloaded-package installation and packaged renderer on macOS."""
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapmatching.minigames import GameStore, LauncherStore, platform_key


def main():
    native = '--native' in sys.argv
    output = ROOT/('out/minigames-native' if native else 'out/minigames')
    catalog = json.loads((output/('native-desktop-games.json' if native else 'desktop-games.json')).read_text())
    info = catalog['game'] if native else catalog['packages'][platform_key()]
    archive = output/info['url'].rsplit('/', 1)[1]
    with tempfile.TemporaryDirectory() as directory:
        store = GameStore(Path(directory))
        if native:
            launcher_info = catalog['launchers'][platform_key()]
            launcher = LauncherStore(Path(directory))
            launcher.install(output/launcher_info['url'].rsplit('/',1)[1], launcher_info['sha256'], launcher_info['size'])
        store.install(archive, info['sha256'], info['size'])
        assert store.installed()
        if sys.platform == 'darwin':
            app = launcher.folder/'GameLauncher.app' if native else store.folder/'Jellyfish.app'
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
        report = output/'startup-smoke.json'
        process = subprocess.Popen([str(store.entry()), '--game-root', str(store.folder/'game'),
            '--profile', str(Path(directory)/'profile'), '--smoke-report', str(report)])
        try:
            result = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        assert result == 0, result
        data = json.loads(report.read_text())
        assert data.get('canvas') and data.get('matter'), data
        if native:
            assert data.get('images',0) >= 16 and data.get('audio',0) >= 15 and data.get('storage'), data
        print('Installed signed game launched:', data)
        # WebView2 releases its user-data lock shortly after the host exits.
        for attempt in range(30):
            try:
                store.root.parent.joinpath('profile/webview2/EBWebView/lockfile').unlink(missing_ok=True)
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.2)


if __name__ == '__main__':
    main()
