"""Phone acceptance regressions, including a real-library positive control."""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'android/app/src/main/python'), str(ROOT)]
from mobile_matching import MobileMatcher, selected_floor, reject_reason
from mapmatching.src.reference import read_image


def candidate(score=.9, contradiction=.08, map_id='a', floor=2):
    return SimpleNamespace(pose=object(), floor=floor, explained=score,
                           contradiction=contradiction, retrieval_score=12, map_id=map_id)


class PolicyTests(unittest.TestCase):
    def test_partial_fit_is_not_success(self):
        self.assertIsNotNone(reject_reason([candidate(.54, .3)]))
        self.assertIsNone(reject_reason([candidate(.56, .39)]))

    def test_ambiguous_identity_is_rejected(self):
        self.assertIsNotNone(reject_reason([candidate(.9), candidate(.87, map_id='b')]))
        self.assertIsNone(reject_reason([candidate(.9), candidate(.87, map_id='b')], floor_confirmed=True))
        self.assertIsNone(reject_reason([candidate(.9), candidate(.7, map_id='b')]))

    def test_selected_floor_and_missing_selector(self):
        from mapmatching.tests.test_floor_tabs import tab_frame
        for floor in (-1, 1, 2):
            self.assertEqual(selected_floor(tab_frame(floor)), floor)
        self.assertIsNone(selected_floor(np.full((648, 1440, 3), 30, np.uint8)))
        self.assertIsNone(selected_floor(np.full((648, 1440, 3), 120, np.uint8)))

    def test_small_distinctive_structure_is_not_rejected_by_size(self):
        matcher = MobileMatcher.__new__(MobileMatcher)
        matcher.floor_references = []
        # Four descriptor anchors, no area/exploration quota. Solver evidence
        # clearly favors one map. An ambiguous fit must still be refused.
        evidence = SimpleNamespace(corners=np.array([[0,0],[0,1],[1,0],[1,1]]), diagnostics={})
        with patch('mobile_matching.extract', return_value=evidence), \
             patch('mobile_matching.retrieve', return_value=[1,2]), \
             patch('mobile_matching.register', side_effect=[candidate(.95), candidate(.7,map_id='b')]):
            self.assertTrue(matcher.match(np.zeros((20,20,3))).candidates)

    def test_real_library_positive_and_wrong_floor(self):
        matcher = MobileMatcher(ROOT/'maps', difficulty='hard')
        reference = next(r for r in matcher.references if r.map_id == 'hard/北-T门')
        region = reference.regions[0]
        x, y, X, Y = region['bbox']
        original = read_image(ROOT/reference.source)
        source = np.zeros_like(original)
        source[y:Y, x:X] = original[y:Y, x:X]
        scale = min(550/(X-x), 480/(Y-y))
        frame = cv2.warpAffine(source, np.array([
            [scale, 0, 900-scale*(x+X)/2], [0, scale, 330-scale*(y+Y)/2]]), (1440, 648))
        start = time.perf_counter()
        result = matcher.match(frame)
        self.assertTrue(result.candidates, result.reason)
        self.assertEqual(result.candidates[0].map_id, reference.map_id)
        print('Positive match ms:', round((time.perf_counter()-start)*1000), result.diagnostics['timing_ms'])
        from mapmatching.src.matcher import MapMatcher
        start = time.perf_counter()
        baseline = MapMatcher._match_view(matcher, frame, full_view=True)
        print('Same-frame uncapped baseline ms:', round((time.perf_counter()-start)*1000))
        self.assertEqual(baseline.candidates[0].map_id, result.candidates[0].map_id)
        matcher.floor_hint = 999
        self.assertFalse(matcher.match(frame).candidates)
        self.assertFalse(matcher.match(np.zeros_like(frame)).candidates)


if __name__ == '__main__':
    unittest.main()
