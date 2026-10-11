"""Exercise the downloaded-package installation and packaged renderer on macOS."""
import json
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapmatching.minigames import GameStore, platform_key


def main():
    output = ROOT/'out/minigames'
    catalog = json.loads((output/'desktop-games.json').read_text())
    info = catalog['packages'][platform_key()]
    archive = output/info['url'].rsplit('/', 1)[1]
    with tempfile.TemporaryDirectory() as directory:
        store = GameStore(Path(directory))
        store.install(archive, info['sha256'], info['size'])
        assert store.installed()
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(store.folder/'Jellyfish.app')], check=True)
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
        print('Installed signed game launched:', data)


if __name__ == '__main__':
    main()
