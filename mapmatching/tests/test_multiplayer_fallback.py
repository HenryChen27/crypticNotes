import unittest
from unittest.mock import Mock

from mapmatching.src.live import MultiplayerFallback, match_with_cache
from mapmatching.src.matcher import MatchResult
from mapmatching.src.types import Candidate, Pose


def candidate(mode):
    return Candidate(f'nightmare/{mode}/test', 'nightmare', mode,
                     8, Pose(1, 10, 20), .8, .1, 1)


class MultiplayerFallbackTests(unittest.TestCase):
    def setUp(self):
        self.duo = Mock(references=[])
        self.solo = Mock(references=[])
        self.factory = Mock(return_value=self.solo)
        self.matcher = MultiplayerFallback(self.duo, self.factory)
        self.duo.match.return_value = MatchResult()
        self.solo.match.return_value = MatchResult(candidates=[candidate('solo')])

    def test_duo_success_does_not_load_solo(self):
        self.duo.match.return_value = MatchResult(candidates=[candidate('duo')])
        result = self.matcher.match(None)
        self.assertEqual(result.candidates[0].mode, 'duo')
        self.factory.assert_not_called()

    def test_duo_failure_uses_solo_with_notice_flag(self):
        result = self.matcher.match(None)
        self.assertEqual(result.candidates[0].mode, 'solo')
        self.assertTrue(result.diagnostics['multiplayer_solo_fallback'])

    def test_both_fail_keeps_primary_result(self):
        self.solo.match.return_value = MatchResult()
        self.assertIs(self.matcher.match(None), self.duo.match.return_value)

    def test_solo_cache_realigns_without_search(self):
        cached = candidate('solo')
        self.solo.register_known.return_value = MatchResult(candidates=[cached])
        result, selected, _ = match_with_cache(self.matcher, None, cached)
        self.assertIs(selected, cached)
        self.assertTrue(result.diagnostics['multiplayer_solo_fallback'])
        self.duo.match.assert_not_called()
        self.solo.match.assert_not_called()

    def test_failed_solo_cache_returns_to_duo_first(self):
        self.solo.register_known.return_value = MatchResult()
        self.duo.match.return_value = MatchResult(candidates=[candidate('duo')])
        _, selected, _ = match_with_cache(self.matcher, None, candidate('solo'))
        self.assertEqual(selected.mode, 'duo')
        self.solo.match.assert_not_called()
