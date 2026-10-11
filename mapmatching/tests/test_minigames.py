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
from mapmatching.minigames import GameStore, package_info, platform_key


class GamePackageTests(unittest.TestCase):
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
