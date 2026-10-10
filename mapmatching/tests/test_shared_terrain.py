import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from mapmatching.src.live import SharedTerrainMatcher, MultiplayerFallback, presentation_candidate
from mapmatching.src.matcher import MatchResult
from mapmatching.src.types import Candidate, Pose


def candidate(mode, floor=1, score=.8):
    return Candidate('nightmare/'+mode+'/test','nightmare',mode,8,Pose(1,10,20),score,.1,floor)


class SharedTerrainTests(unittest.TestCase):
    def test_duo_fallback_reuses_current_support_without_searching_twice(self):
        primary=Mock(references=[SimpleNamespace(terrain_id='pair')])
        alternate=Mock(references=[])
        rejected=MatchResult()
        primary._match_view.return_value=rejected
        primary.match.return_value=rejected
        alternate.match.return_value=MatchResult()
        shared=SharedTerrainMatcher(primary,lambda:alternate)
        factory=Mock()
        matcher=MultiplayerFallback(shared,factory)
        for frame in (object(),object()):
            before=alternate.match.call_count
            self.assertIs(matcher.match(frame),rejected)
            self.assertEqual(alternate.match.call_count,before+1)
            alternate.match.assert_called_with(frame)
        factory.assert_not_called()
        primary._match_view.return_value=MatchResult(candidates=[candidate('duo')])
        matcher.match(object())
        self.assertIsNone(shared.last_support)

    def setUp(self):
        self.primary=Mock(references=[SimpleNamespace(map_id='nightmare/solo/test',terrain_id='terrain')])
        self.other=Mock(references=[SimpleNamespace(map_id='nightmare/duo/test',terrain_id='terrain')])
        self.rejected=MatchResult()
        self.primary._match_view.return_value=self.rejected
        self.primary.match.return_value=self.rejected
        self.primary.register_known.return_value=MatchResult(candidates=[candidate('solo')])
        self.other.match.return_value=MatchResult(candidates=[candidate('duo')])
        self.factory=Mock(return_value=self.other)
        self.matcher=SharedTerrainMatcher(self.primary,self.factory)

    def test_support_preserves_selected_route_and_own_pose(self):
        result=self.matcher.match(None)
        chosen=presentation_candidate(result)[0]
        self.assertEqual(chosen.mode,'solo')
        self.assertIs(chosen,self.primary.register_known.return_value.candidates[0])
        self.assertIn('terrain_support',result.diagnostics)

    def test_normal_match_does_not_load_alternate(self):
        self.primary._match_view.return_value=MatchResult(candidates=[candidate('solo')])
        self.matcher.match(None)
        self.factory.assert_not_called()

    def test_unpaired_or_wrong_floor_or_weak_alignment_cannot_unlock(self):
        for kind in ('unpaired','floor','weak','ambiguous'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind=='unpaired':self.other.references[0].terrain_id=None
                if kind=='floor':self.primary.register_known.return_value=MatchResult(candidates=[candidate('solo',2)])
                if kind=='weak':self.primary.register_known.return_value=MatchResult(candidates=[candidate('solo',score=.6)])
                if kind=='ambiguous':self.other.match.return_value.candidates.append(candidate('duo'))
                self.assertIs(self.matcher.match(None),self.rejected)

    def test_cached_route_stays_in_selected_library(self):
        self.matcher.floor_hint=2
        self.matcher.register_known(None,'nightmare/solo/test')
        self.assertEqual(self.primary.floor_hint,2)
        self.factory.assert_not_called()
