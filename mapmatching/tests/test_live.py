import unittest
import numpy as np
from mapmatching.src.live import ToggleState, presentation_candidate, raw_layer, composite
from mapmatching.src.matcher import MatchResult
from mapmatching.src.types import Candidate,Pose
from mapmatching.src.reference import Reference


class LiveTests(unittest.TestCase):
    def test_close_and_reopen_reject_late_result(self):
        state = ToggleState()
        old = state.open()
        state.close()
        self.assertFalse(state.accepts(old))
        new = state.open()
        self.assertFalse(state.accepts(old))
        self.assertTrue(state.accepts(new))

    def candidate(self,score=.8):
        return Candidate('test','hard',None,8,Pose(1,0,0),score,.1,1)

    def test_weak_missing_and_ambiguous_are_not_displayed(self):
        for result in [MatchResult(), MatchResult(candidates=[self.candidate(.4)]),
                       MatchResult(candidates=[self.candidate(.8),self.candidate(.799)])]:
            self.assertIsNone(presentation_candidate(result)[0])
        c = self.candidate()
        c.floor = None
        self.assertIsNone(presentation_candidate(MatchResult(candidates=[c]))[0])

    def test_preview_does_not_promote_unknown_to_lock(self):
        result=MatchResult(candidates=[self.candidate()])
        self.assertIsNotNone(presentation_candidate(result)[0])
        self.assertEqual(result.status,'UNKNOWN')

    def test_raw_original_colors_and_thirty_percent(self):
        original = np.full((100,100,3),(100,150,200),np.uint8)
        reference=Reference('test','hard',None,'unused',None,None,[{'floor':1,'bbox':[0,0,100,60]}],[[40,40,45,45]])
        layer=raw_layer(original.shape,original,reference,self.candidate())
        np.testing.assert_array_equal(layer[30,30],[100,150,200,255])
        self.assertEqual(layer[70,30,3],0)
        self.assertEqual(layer[42,42,3],0)
        self.assertEqual(layer[10,30,3],0)
        screen=np.full_like(original,20)
        result=composite(screen,layer)
        np.testing.assert_array_equal(result[30,30],[44,59,74])
        np.testing.assert_array_equal(result[70,30],screen[70,30])

    def test_missing_floor_rejected(self):
        ref=Reference('test','hard',None,'unused',None,None)
        with self.assertRaises(ValueError):
            raw_layer((100,100,3),np.zeros((100,100,3),np.uint8),ref,self.candidate())


if __name__ == '__main__':
    unittest.main()
