"""Phone cross-floor consent/cache regressions without a device."""
import sys,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from dataclasses import replace
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'android/app/src/main/python')]
import mobile_bridge as bridge
from mapmatching.src.types import Candidate,Pose
from mapmatching.src.matcher import MatchResult

class ManualTests(unittest.TestCase):
    def setUp(self):
        self.known=Candidate('hard/known','hard',None,8,Pose(1,0,0),.8,.1,1)
        self.ref=SimpleNamespace(map_id=self.known.map_id,source='map.jpg',difficulty='hard',mode=None,
            regions=[{'floor':1,'bbox':[0,0,50,50]},{'floor':2,'bbox':[0,50,50,100]}],exclusions=[])
        self.matcher=SimpleNamespace(references=[self.ref],
                                    register_manual_floor=Mock(return_value=MatchResult()))
        bridge._matcher=self.matcher;bridge._confirmed=self.known;bridge._cached=self.known
        bridge._root=ROOT;bridge._originals.clear();bridge._pending_candidate=None
        self.patches=[patch('mobile_bridge.decode',return_value=np.zeros((100,200,3),np.uint8)),
            patch('mobile_bridge.inspect_map_ui',return_value={'visible':True}),
            patch('mobile_bridge.selected_floor',return_value=2),
            patch('mobile_bridge.read_image',return_value=np.zeros((100,50,3),np.uint8)),
            patch('mobile_bridge.match_with_cache',return_value=(MatchResult(),None,'insufficient'))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def call(self,force=0):
        with tempfile.TemporaryDirectory() as folder:
            return json.loads(bridge.match(b'',str(Path(folder)/'overlay.png'),force_floor=force,remember=False,token=12))

    def test_offer_force_then_next_request_requires_consent_again(self):
        self.assertEqual(self.call()['manual_offer']['floor'],2)
        forced=self.call(2)
        self.assertTrue(forced['ok'])
        bridge.commit_match(12)
        self.assertIs(bridge._confirmed,self.known);self.assertIs(bridge._cached,self.known)
        self.assertEqual(self.call()['manual_offer']['floor'],2)

    def test_floor_changed_cancels_consent(self):
        with patch('mobile_bridge.selected_floor',return_value=1):
            self.assertFalse(self.call(2)['ok'])

    def test_geometric_force_is_one_shot_and_restores_search_bounds(self):
        aligned=replace(self.known,floor=2)
        self.matcher.register_manual_floor.return_value=MatchResult(candidates=[aligned])
        self.assertTrue(self.call(2)['ok'])
        self.assertIsNone(self.matcher.manual_scale_bounds)
        self.assertIsNone(bridge._pending_candidate)
        self.assertIs(bridge._confirmed,self.known)

    def test_strong_current_floor_keeps_normal_automatic_matching(self):
        aligned=replace(self.known,floor=2)
        with patch('mobile_bridge.match_with_cache',return_value=(MatchResult(candidates=[aligned]),aligned,'matched')):
            result=self.call()
        self.assertTrue(result['ok']);self.assertNotIn('manual_offer',result)
        bridge.commit_match(12)
        self.assertIs(bridge._confirmed,aligned)

    def test_sparse_auto_fit_cannot_bypass_offer(self):
        weak=replace(self.known,floor=2,retrieval_score=2,pose=Pose(.1,0,0))
        with patch('mobile_bridge.match_with_cache',return_value=(MatchResult(candidates=[weak]),weak,'cached')):
            self.assertIn('manual_offer',self.call())

    def test_reverse_floor_switch_and_unconfirmed_identity(self):
        bridge._confirmed=replace(self.known,floor=2)
        with patch('mobile_bridge.selected_floor',return_value=1):
            self.assertEqual(self.call()['manual_offer']['floor'],1)
        bridge._confirmed=None
        self.assertNotIn('manual_offer',self.call())

if __name__=='__main__':unittest.main()
