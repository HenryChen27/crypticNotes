import unittest
import numpy as np
from mapmatching.game_scene_watch import SceneDetector,difference,sample_frame

class SceneTests(unittest.TestCase):
    def setUp(self):
        self.base=np.random.default_rng(12).integers(30,180,(180,320,3),dtype=np.uint8)
    def test_low_motion_arms_then_large_change_triggers_once(self):
        detector=SceneDetector()
        self.assertIsNone(detector.feed(self.base))
        slow=self.base.copy();slow[20:25,20:25]=240
        self.assertIsNone(detector.feed(slow));self.assertTrue(detector.armed)
        changed=np.clip(self.base.astype(int)-45,0,255).astype(np.uint8)
        self.assertGreater(detector.feed(changed)['changed_fraction'],.25)
        self.assertIsNone(detector.feed(changed))
    def test_black_capture_and_resize_do_not_trigger(self):
        detector=SceneDetector();detector.feed(self.base);detector.feed(self.base)
        self.assertIsNone(detector.feed(np.zeros_like(self.base)))
        self.assertIsNone(detector.feed(self.base[:100,:100]));self.assertFalse(detector.armed)
    def test_needs_stable_history_not_arbitrary_first_frame(self):
        detector=SceneDetector();detector.feed(self.base)
        changed=np.clip(self.base.astype(int)-45,0,255).astype(np.uint8)
        self.assertIsNone(detector.feed(changed));self.assertFalse(detector.armed)

if __name__=='__main__':unittest.main()
