import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from mapmatching.src.live import worker
from mapmatching.src.matcher import MatchResult
from mapmatching.src.types import Candidate, Pose


class ClosedMapFallbackTests(unittest.TestCase):
    def test_rejected_scene_never_renders_cached_map(self):
        cached = Candidate('nightmare/solo/old', 'nightmare', 'solo', 8,
                           Pose(1, 0, 0), .8, .1, 1)
        for anchors in (50, 350):
            for identity in (cached.map_id, 'nightmare/solo/other'):
                with self.subTest(anchors=anchors, identity=identity):
                    rejected = Candidate(identity, 'nightmare', 'solo', 3,
                                         Pose(1, 0, 0), .2, .8, 2)
                    result = MatchResult(candidates=[rejected], diagnostics={'anchors': anchors})
                    reference = SimpleNamespace(map_id=cached.map_id, source='unused',
                                                regions=[{'floor': 2, 'bbox': [0,0,100,100]}])
                    matcher = Mock(references=[reference])
                    matcher.match.return_value = result
                    matcher.register_known.return_value = result
                    connection = Mock()
                    connection.recv.side_effect = [(1,np.zeros((200,300,3),np.uint8),cached),None]
                    with patch('mapmatching.src.matcher.MapMatcher', return_value=matcher), \
                         patch('mapmatching.src.reference.read_image') as read:
                        worker(connection, Path(__file__).resolve().parents[2], 'nightmare', 'solo')
                    kind, payload = connection.send.call_args_list[1].args[0]
                    self.assertEqual(kind, 'result')
                    self.assertIsNone(payload[1])
                    self.assertIsNone(payload[3])
                    read.assert_not_called()

