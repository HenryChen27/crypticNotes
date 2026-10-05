"""Exercise deferred cache commits without an Android device."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'android/app/src/main/python')]
import mobile_bridge as bridge


class CacheTests(unittest.TestCase):
    def test_only_matching_request_can_commit(self):
        bridge._cached=None
        candidate=object()
        bridge._pending_candidate=(12,candidate)
        bridge.commit_match(11)
        self.assertIsNone(bridge._cached)
        bridge.commit_match(12)
        self.assertIs(bridge._cached,candidate)
        self.assertIsNone(bridge._pending_candidate)

    def test_previous_result_cannot_replace_new_proposal(self):
        bridge._cached=None
        bridge._pending_candidate=(14,object())
        bridge.commit_match(12)
        self.assertIsNone(bridge._cached)


if __name__=='__main__':unittest.main()
