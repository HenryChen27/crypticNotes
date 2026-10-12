"""Optional package lifecycle, download integrity and extraction boundaries."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
import sys
from pathlib import Path
from unittest.mock import patch
from mapmatching.minigames import GameStore, LauncherStore, package_info, platform_key


class GamePackageTests(unittest.TestCase):
    def test_same_launcher_version_requires_matching_download_hash(self):
        launcher = LauncherStore(self.root)
        launcher.folder.mkdir(parents=True)
        metadata = {'version': '2.4.0', 'downloadSha256': 'a' * 64}
        (launcher.folder/'package.json').write_text(json.dumps(metadata))
        self.assertTrue(launcher.matches_download({'version': '2.4.0', 'sha256': 'a' * 64}))
        self.assertFalse(launcher.matches_download({'version': '2.4.0', 'sha256': 'b' * 64}))
        metadata.pop('downloadSha256')
        (launcher.folder/'package.json').write_text(json.dumps(metadata))
        self.assertFalse(launcher.matches_download({'version': '2.4.0', 'sha256': 'a' * 64}))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = GameStore(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def bundle(self, extra=None, game_id='jellyfish'):
        archive = self.root/'bundle.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('package.json', json.dumps({'id':game_id, 'platform':platform_key()}))
            z.writestr(self.store.entry().relative_to(self.store.folder).as_posix(), b'executable fixture')
            z.writestr('game/index.html', b'<canvas></canvas>')
            if extra:
                z.writestr(*extra)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_install_delete_preserves_preferences(self):
        profile = self.root/'minigame-saves/jellyfish/audio.json'
        profile.parent.mkdir(parents=True)
        profile.write_text('{"music":0.3}')
        archive, checksum = self.bundle()
        self.store.install(archive, checksum, archive.stat().st_size)
        self.assertTrue(self.store.installed())
        self.assertGreater(self.store.size(), 0)
        self.store.delete()
        self.assertFalse(self.store.installed())
        self.assertEqual(profile.read_text(), '{"music":0.3}')

    def native_bundle(self, launcher=False, game_id='jellyfish'):
        archive = self.root/('runtime.zip' if launcher else game_id+'.zip')
        metadata = {'id':'game-launcher' if launcher else game_id,'version':'2.0.0'}
        with zipfile.ZipFile(archive,'w') as z:
            if launcher:
                metadata['platform'] = platform_key()
                host = LauncherStore(self.root)
                z.writestr(host.entry().relative_to(host.folder).as_posix(), b'native host')
            else:
                metadata['runtime'] = 'system-webview'
                z.writestr('game/index.html',b'game')
            z.writestr('package.json',json.dumps(metadata))
        info = {'version':'2.0.0','size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                'url':'https://github.com/HenryChen27/Jellyfish/releases/download/desktop-v2.0.0/'+archive.name}
        return archive,info

    def test_shared_launcher_survives_game_delete_and_is_reused(self):
        runtime, runtime_info = self.native_bundle(launcher=True)
        game, game_info = self.native_bundle()
        launcher = LauncherStore(self.root)
        launcher.install(runtime,runtime_info['sha256'])
        self.store.install(game,game_info['sha256'])
        self.assertEqual(self.store.entry(),launcher.entry())
        self.assertTrue(self.store.native())
        other = GameStore(self.root,'second-game')
        second, second_info = self.native_bundle(game_id='second-game')
        other.install(second,second_info['sha256'])
        self.assertEqual(other.entry(),launcher.entry())
        self.store.delete()
        self.assertTrue(launcher.installed())
        self.assertTrue(launcher.satisfies('1.0.0'))
        self.assertFalse(launcher.satisfies('3.0.0'))
        self.assertTrue(other.installed())
        catalog = {'schema':2,'id':'jellyfish','game':game_info,'launchers':{platform_key():runtime_info}}
        with patch('mapmatching.minigames.read_catalog',return_value=catalog), \
             patch.object(LauncherStore,'download_package') as download_runtime, \
             patch('mapmatching.minigames.urllib.request.urlopen',return_value=io.BytesIO(game.read_bytes())):
            self.store.download(lambda *args:None)
            download_runtime.assert_not_called()
        self.assertTrue(self.store.installed())

    def test_native_game_requires_launcher_and_failed_upgrade_keeps_legacy(self):
        legacy, checksum = self.bundle()
        self.store.install(legacy,checksum)
        before = self.store.entry().read_bytes()
        game, info = self.native_bundle()
        with self.assertRaises(ValueError):
            self.store.install(game,info['sha256'])
        self.assertEqual(self.store.entry().read_bytes(),before)
        self.assertFalse(self.store.native())

    def test_bad_checksum_or_wrong_platform_does_not_replace_installed_game(self):
        archive, checksum = self.bundle()
        self.store.install(archive, checksum)
        before = self.store.entry().read_bytes()
        with self.assertRaises(ValueError):
            self.store.install(archive, '0'*64)
        archive, checksum = self.bundle(game_id='different-game')
        with self.assertRaises(ValueError):
            self.store.install(archive, checksum)
        self.assertEqual(self.store.entry().read_bytes(), before)

    def test_rejects_path_escape_windows_paths_and_symlinks(self):
        for name in ('../escaped', '/absolute', 'C:/absolute', '..\\escaped'):
            with self.subTest(name=name):
                archive, checksum = self.bundle((name, b'bad'))
                with self.assertRaises(ValueError):
                    self.store.install(archive, checksum)
                self.assertFalse(self.store.installed())
        link = zipfile.ZipInfo('game/link')
        link.external_attr = 0o120777 << 16
        archive, checksum = self.bundle((link, b'../../escaped'))
        with self.assertRaises(ValueError):
            self.store.install(archive, checksum)

    @unittest.skipUnless(sys.platform == 'darwin', 'Signed app links are macOS only')
    def test_mac_framework_links_and_escape(self):
        link = zipfile.ZipInfo('Jellyfish.app/Contents/Frameworks/Fixture.framework/Versions/Current')
        link.external_attr = 0o120777 << 16
        archive, _ = self.bundle()
        with zipfile.ZipFile(archive, 'a') as z:
            z.writestr('Jellyfish.app/Contents/Frameworks/Fixture.framework/Versions/A/data', b'framework')
            z.writestr(link, b'A')
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.store.install(archive, checksum)
        self.assertEqual((self.store.folder/link.filename/'data').read_bytes(), b'framework')
        archive, checksum = self.bundle((link, b'../../../../../../escaped'))
        with self.assertRaises(ValueError):
            self.store.install(archive, checksum)
        self.assertTrue(self.store.installed())

    def test_wrong_download_size_and_cancel_leave_no_install(self):
        archive, checksum = self.bundle()
        with self.assertRaises(ValueError):
            self.store.install(archive, checksum, archive.stat().st_size+1)
        info = {'url':'https://github.com/HenryChen27/Jellyfish/releases/download/v1/game.zip',
                'size':archive.stat().st_size, 'sha256':checksum}
        catalog = {'schema':1,'id':'jellyfish','packages':{platform_key():info}}
        with patch('mapmatching.minigames.read_catalog', return_value=catalog), \
             patch('mapmatching.minigames.urllib.request.urlopen', return_value=io.BytesIO(archive.read_bytes())):
            with self.assertRaises(InterruptedError):
                self.store.download(lambda *args: None, lambda: True)
        self.assertFalse((self.store.root/'.jellyfish-download.zip').exists())
        self.assertFalse(self.store.installed())

    def test_download_installs_verified_bundle(self):
        archive, checksum = self.bundle()
        info = {'url':'https://github.com/HenryChen27/Jellyfish/releases/download/v1/game.zip',
                'size':archive.stat().st_size, 'sha256':checksum}
        catalog = {'schema':1,'id':'jellyfish','packages':{platform_key():info}}
        events = []
        with patch('mapmatching.minigames.read_catalog', return_value=catalog), \
             patch('mapmatching.minigames.urllib.request.urlopen', return_value=io.BytesIO(archive.read_bytes())):
            self.store.download(lambda *args: events.append(args))
        self.assertTrue(self.store.installed())
        self.assertEqual(events[-1][0], 100)
        self.assertFalse((self.store.root/'.jellyfish-download.zip').exists())

    def test_missing_system_package_or_untrusted_url_is_rejected(self):
        with self.assertRaises(ValueError):
            package_info({'packages':{}})
        with self.assertRaises(ValueError):
            package_info({'packages':{platform_key():{'url':'http://example.com/game.zip'}}})

    def test_minigame_window_is_not_a_map_matching_target(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from mapmatching.ui import Companion, win32gui
        subject=SimpleNamespace(minigames=SimpleNamespace(owns_window=Mock(return_value=True)))
        with patch.object(win32gui,'IsWindow',return_value=True), patch.object(win32gui,'IsIconic',return_value=False):
            self.assertFalse(Companion.is_game(subject,12345))
        subject.minigames.owns_window.assert_called_once_with(12345)


if __name__ == '__main__':
    unittest.main()
