from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mapmatching.src import mapstore
from mapmatching.src.map_admin import delete_map


class DeleteMapTests(unittest.TestCase):
    def setup_map(self, root):
        maps = root/'maps'
        (maps/'hard').mkdir(parents=True)
        (maps/'evidence').mkdir()
        entry = dict(map_id='hard/test', source='maps/hard/test.png')
        (maps/'hard/test.png').write_bytes(b'image')
        (maps/'evidence'/mapstore.evidence_name(entry['map_id'])).write_bytes(b'features')
        mapstore.write_manifest(maps, [entry])
        mapstore.write_json(maps/'index.json', dict(references=[entry]))
        return maps, entry

    def test_deletes_disabled_map_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps, entry = self.setup_map(root)
            mapstore.set_map_enabled(maps, entry['map_id'], False)
            delete_map(root, entry['map_id'])
            self.assertEqual(mapstore.read_disabled(maps), [])
            self.assertEqual(mapstore.read_manifest(maps), [])
            self.assertEqual(mapstore._read_json(maps/'index.json', {})['references'], [])
            self.assertFalse((root/entry['source']).exists())
            self.assertEqual(list((maps/'evidence').iterdir()), [])

    def test_rejects_external_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps, entry = self.setup_map(root)
            entry['source'] = 'external.png'
            (root/'external.png').write_bytes(b'keep')
            mapstore.write_manifest(maps, [entry])
            with self.assertRaises(ValueError):
                delete_map(root, entry['map_id'])
            self.assertEqual((root/'external.png').read_bytes(), b'keep')
            self.assertEqual(mapstore.read_manifest(maps), [entry])

    def test_shared_source_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps, entry = self.setup_map(root)
            other = dict(entry, map_id='hard/other')
            mapstore.write_manifest(maps, [entry, other])
            delete_map(root, entry['map_id'])
            self.assertTrue((root/entry['source']).exists())
            self.assertEqual(mapstore.read_manifest(maps), [other])

    def test_write_failure_restores_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps, entry = self.setup_map(root)
            with patch.object(mapstore, 'write_manifest', side_effect=OSError('locked')):
                with self.assertRaises(OSError):
                    delete_map(root, entry['map_id'])
            self.assertEqual((root/entry['source']).read_bytes(), b'image')
            self.assertEqual(mapstore.read_manifest(maps), [entry])
