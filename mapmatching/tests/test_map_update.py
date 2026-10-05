import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mapmatching.src.map_update import merge, install, stamp, read, write


class MapUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = self.root/'old/maps'
        self.new = self.root/'new/maps'
        for p in (self.old, self.new):
            p.mkdir(parents=True)
            write(p/'floors.json', {'references': []})

    def add(self, maps, name, content, disabled=False):
        (maps/(name+'.png')).write_text(content)
        key, filename = ('records','disabled.json') if disabled else ('references','floors.json')
        data = read(maps/filename, {key: []})
        data[key].append({'map_id': name, 'source': 'maps/'+name+'.png'})
        write(maps/filename, data)

    @patch('mapmatching.src.mapstore.build_index')
    def test_official_replaced_removed_custom_and_disabled_preserved(self, build):
        self.add(self.old, 'official', 'old')
        self.add(self.old, 'removed', 'old')
        stamp(self.old)
        self.add(self.old, 'custom', 'user')
        self.add(self.old, 'hidden', 'user', disabled=True)
        self.add(self.new, 'official', 'new')
        merge(self.old, self.new)
        self.assertEqual((self.new/'official.png').read_text(), 'new')
        self.assertFalse((self.new/'removed.png').exists())
        self.assertEqual((self.new/'custom.png').read_text(), 'user')
        self.assertEqual(read(self.new/'disabled.json', {})['records'][0]['map_id'], 'hidden')
        self.assertEqual(read(self.new/'official-library.json', {})['ids'], ['official'])
        build.assert_called_once_with(self.new)

    @patch('mapmatching.src.mapstore.build_index')
    def test_legacy_keeps_unknown(self, build):
        self.add(self.old, 'local', 'user')
        self.add(self.new, 'official', 'new')
        merge(self.old, self.new)
        self.assertEqual(len(read(self.new/'floors.json', {})['references']), 2)
        self.assertTrue((self.old/'local.png').exists())

    def test_collision_aborts_before_replacing_user_map(self):
        stamp(self.old)
        self.add(self.old, 'same', 'user')
        self.add(self.new, 'same', 'official')
        with self.assertRaises(ValueError):
            merge(self.old, self.new)
        self.assertEqual((self.old/'same.png').read_text(), 'user')

    @patch('mapmatching.src.mapstore.build_index', side_effect=RuntimeError('bad map'))
    def test_android_merge_failure_keeps_live_library(self, build):
        self.add(self.old, 'custom', 'user')
        with self.assertRaises(RuntimeError):
            install(self.old.parent, self.new)
        self.assertEqual((self.old/'custom.png').read_text(), 'user')

    def test_android_install_and_recovery(self):
        self.add(self.new, 'official', 'new')
        backup = self.old.parent/'maps-update-backup'
        self.old.rename(backup)
        install(self.old.parent, self.new)
        self.assertEqual((self.old/'official.png').read_text(), 'new')
        self.assertTrue(backup.exists())

    def test_traversal_rejected(self):
        write(self.old/'floors.json', {'references': [{'map_id':'x', 'source':'maps/../../outside.png'}]})
        with self.assertRaises(ValueError):
            merge(self.old, self.new)


if __name__ == '__main__':
    unittest.main()
