"""Contract checks on synthetic geometry; not evidence of real-image accuracy."""
import unittest
import cv2
import numpy as np
from mapmatching.src.evidence import extract
from mapmatching.src.reference import Reference
from mapmatching.src.retrieval import Retrieved, retrieve
from mapmatching.src.registration import register
from mapmatching.src.types import Evidence
from mapmatching.src.verification import verify
from mapmatching.src.matcher import MatchResult, MatchSession


def reference(boundary: np.ndarray, factor: float = 1.) -> Reference:
    ev = Evidence(boundary.copy(), boundary, np.empty((0, 2), np.float32),
                  np.empty((0, 144), np.float32), np.empty(0), factor, None)
    return Reference('synthetic', 'test', None, 'synthetic', ev,
                     cv2.distanceTransform(1-boundary, cv2.DIST_L2, 3))


class GeometryTests(unittest.TestCase):
    def test_invalid_pixel_input_fails_clearly(self):
        for value in (np.zeros((10, 10), np.uint8), np.zeros((10, 10, 3), np.float32), np.empty((0, 0, 3), np.uint8)):
            with self.assertRaises(ValueError):
                extract(value)

    def test_session_requires_explicit_rematch_to_replace_lock(self):
        class FakeMatcher:
            calls = 0
            def match(self, screenshot):
                self.calls += 1
                return MatchResult(status='MATCHED', map_id=str(self.calls))
        matcher = FakeMatcher()
        session = MatchSession(matcher)
        pixels = np.zeros((10, 10, 3), np.uint8)
        self.assertEqual(session.match(pixels).map_id, '1')
        self.assertEqual(session.match(pixels).map_id, '1')
        self.assertEqual(matcher.calls, 1)
        self.assertEqual(session.rematch(pixels).map_id, '2')
        session.unlock()
        self.assertEqual(session.match(pixels).map_id, '3')

    def test_hidden_reference_structure_has_no_penalty(self):
        edge = np.zeros((100, 100), np.uint8)
        edge[20, 20:40] = 1
        points = np.column_stack((np.arange(20, 40), np.full(20, 20))).astype(np.float32)
        original = verify(np.array([1., 0, 0]), points, reference(edge))
        edge[80, 60:90] = 1  # Additional structure outside observed region.
        self.assertEqual(original, verify(np.array([1., 0, 0]), points, reference(edge)))
        self.assertEqual(original, (1., 0.))

    def test_outside_reference_is_contradiction(self):
        edge = np.zeros((100, 100), np.uint8)
        edge[20, 20:40] = 1
        explained, contradiction = verify(np.array([1., 0, 0]), np.array([[-20., -20.]], np.float32), reference(edge))
        self.assertEqual((explained, contradiction), (0., 1.))

    def test_empty_image_does_not_propose_a_map(self):
        ev = extract(np.zeros((200, 300, 3), np.uint8))
        refs = [reference(np.zeros((100, 100), np.uint8))]
        result = retrieve(ev, refs)[0]
        self.assertEqual(result.score, 0.)
        self.assertEqual(len(result.hypotheses), 0)
        self.assertIsNone(register(ev, result).pose)

    def test_pose_restores_original_coordinate_system(self):
        boundary = np.zeros((100, 100), np.uint8)
        cv2.rectangle(boundary, (20, 20), (50, 60), 1, 1)
        ref = reference(boundary, factor=.5)
        game_boundary = cv2.warpAffine(boundary, np.array([[2., 0, 15], [0, 2., 12]]), (220, 220), flags=cv2.INTER_NEAREST)
        ev = Evidence(game_boundary, game_boundary, np.empty((0, 2)), np.empty((0, 144)), np.empty(0), .25, None)
        fitted = register(ev, Retrieved(ref, 5., np.array([[2., 15., 12.]]), 4))
        self.assertIsNotNone(fitted.pose)
        self.assertAlmostEqual(fitted.pose.scale, 4., delta=.1)
        self.assertAlmostEqual(fitted.pose.tx, 60., delta=4.)
        self.assertAlmostEqual(fitted.pose.ty, 48., delta=4.)


if __name__ == '__main__':
    unittest.main()
