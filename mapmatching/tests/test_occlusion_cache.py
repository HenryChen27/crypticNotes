import unittest
from unittest.mock import Mock
import cv2
import numpy as np
from mapmatching.src.occlusion import control_panels
from mapmatching.src.live import match_with_cache
from mapmatching.src.matcher import MatchResult
from mapmatching.src.types import Candidate,Pose


def candidate(score=.8):
    return Candidate('hard/test','hard',None,8,Pose(1,10,20),score,.15,1)


class OcclusionCacheTests(unittest.TestCase):
    def test_stacked_controls_detected_at_different_positions(self):
        for offset in (80,680):
            image=np.zeros((625,1000,3),np.uint8)
            for y,w in [(100,80),(220,160),(280,80),(360,160)]:
                cv2.rectangle(image,(offset,y),(offset+w,y+22),(150,150,150),-1)
            boxes=control_panels(image)
            self.assertTrue(any(x0<=offset and x1>=offset+160 and y0<=100 and y1>=382 for x0,y0,x1,y1 in boxes))

    def test_one_room_is_not_a_control_panel(self):
        image=np.zeros((625,1000,3),np.uint8)
        cv2.rectangle(image,(300,250),(450,280),(150,150,150),-1)
        self.assertEqual(control_panels(image),[])

    def test_cache_success_never_searches_library(self):
        matcher=Mock()
        current=candidate()
        current.pose=Pose(1.5,100,200)
        matcher.register_known.return_value=MatchResult(candidates=[current])
        result,c,_=match_with_cache(matcher,np.zeros((5,5,3),np.uint8),candidate())
        matcher.match.assert_not_called()
        self.assertEqual(c.pose,Pose(1.5,100,200))
        self.assertFalse(result.diagnostics['identity_search_performed'])

    def test_bad_cached_alignment_falls_back(self):
        matcher=Mock()
        matcher.register_known.return_value=MatchResult(candidates=[candidate(.6)])
        matcher.match.return_value=MatchResult(candidates=[candidate(.85)])
        result,c,_=match_with_cache(matcher,np.zeros((5,5,3),np.uint8),candidate())
        matcher.match.assert_called_once()
        self.assertEqual(result.diagnostics['pipeline'],'recognition_fallback')

    def test_floor_hint_updates_before_alignment_and_clears_when_unknown(self):
        from mapmatching.tests.test_floor_tabs import tab_frame
        matcher=Mock()
        matcher.floor_hint=None
        matcher.match.return_value=MatchResult()
        for floor in (-1,2,1,None):
            match_with_cache(matcher,tab_frame(floor))
            self.assertEqual(matcher.floor_hint,floor)

    def test_empty_cache_recognizes(self):
        matcher=Mock()
        matcher.match.return_value=MatchResult()
        result,c,_=match_with_cache(matcher,np.zeros((5,5,3),np.uint8))
        matcher.register_known.assert_not_called()
        self.assertIsNone(c)

    def test_strong_new_floor_does_not_search_all_maps(self):
        matcher=Mock()
        previous=candidate(.98)
        current=candidate(.80)
        current.floor=2
        matcher.register_known.return_value=MatchResult(candidates=[current])
        _, selected, _=match_with_cache(matcher,None,previous)
        self.assertIs(selected,current)
        matcher.match.assert_not_called()

    def test_weak_other_map_does_not_replace_remembered_map(self):
        matcher=Mock()
        previous=candidate()
        other=candidate(.65);other.map_id='hard/other'
        matcher.register_known.return_value=MatchResult()
        matcher.match.return_value=MatchResult(candidates=[other])
        result,selected,_=match_with_cache(matcher,None,previous)
        self.assertIsNone(selected)
        self.assertEqual(previous.map_id,'hard/test')
        self.assertEqual(result.diagnostics['map_switch_rejected'],'hard/other')

    def test_strong_unambiguous_other_map_can_replace_cache(self):
        matcher=Mock()
        other=candidate(.9);other.map_id='hard/other'
        matcher.register_known.return_value=MatchResult()
        matcher.match.return_value=MatchResult(candidates=[other,candidate(.7)])
        _,selected,_=match_with_cache(matcher,None,candidate())
        self.assertIs(selected,other)


if __name__=='__main__':
    unittest.main()
