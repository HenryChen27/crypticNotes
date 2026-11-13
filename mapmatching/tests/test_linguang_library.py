"""磷光症 library contexts: every author offers 困难 and 噩梦 (2026-11-13)."""
import unittest
from pathlib import Path
from mapmatching.src.context import SessionContext, scene_options
from mapmatching.src import mapstore

ROOT = Path(__file__).resolve().parents[2]


class LinguangContextTests(unittest.TestCase):
    def test_lianghapi_offers_hard_and_nightmare_without_party(self):
        self.assertEqual(scene_options('linguang', 'lianghapi'), (('hard', 'nightmare'), (None,)))
        SessionContext('hard', None, 'lianghapi', 'linguang')
        SessionContext('nightmare', None, 'lianghapi', 'linguang')
        for mode in ('solo', 'duo', 'full'):
            with self.assertRaises(ValueError):
                SessionContext('nightmare', mode, 'lianghapi', 'linguang')

    def test_lianghapi_nightmare_atlases_are_registered_with_three_basements(self):
        entries = [e for e in mapstore.read_manifest(ROOT/'maps')
                   if e.get('scene') == 'linguang' and e['provider'] == 'lianghapi' and e['difficulty'] == 'nightmare']
        self.assertEqual(len(entries), 15)
        for e in entries:
            self.assertIsNone(e['mode'])
            self.assertTrue(e['map_id'].startswith('linguang/lianghapi/nightmare/'))
            self.assertEqual([r['floor'] for r in e['regions']], [-1, -2, -3])
            self.assertTrue((ROOT/e['source']).is_file(), e['source'])
            self.assertEqual(e['storage']['policy'], 'webp-2048-q90-v1')
            w, h = e['size']
            tops = [r['bbox'][1] for r in e['regions']]
            self.assertEqual(tops, sorted(tops))
            self.assertTrue(all(0 <= r['bbox'][1] < r['bbox'][3] <= h and r['bbox'][2] <= w for r in e['regions']))


if __name__ == '__main__':
    unittest.main()
