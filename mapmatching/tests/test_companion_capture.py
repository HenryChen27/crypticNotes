import unittest
from unittest.mock import Mock,patch
import numpy as np
from mapmatching.src.windows import mask_screen_rect


class CompanionCaptureTests(unittest.TestCase):
    def test_screen_mask_clips_at_monitor_boundary(self):
        image=np.ones((100,200,3),np.uint8)
        mask_screen_rect(image,(-200,100,200,100),(-220,120,50,40))
        self.assertFalse(image[20:60,:30].any())
        self.assertTrue(image[:,30:].all())
        mask_screen_rect(image,(-200,100,200,100),(500,100,40,40))
        self.assertTrue(image[:,30:].all())

    def test_repeated_capture_does_not_toggle_companion_visibility(self):
        from mapmatching.ui import Companion,C
        subject=Mock()
        subject.state.accepts.return_value=True
        subject.foreground_lost.return_value=False
        with patch.object(C.QTimer,'singleShot') as timer:
            for _ in range(6):
                Companion.take_capture(subject,1)
        subject.hide.assert_not_called()
        subject.show.assert_not_called()
        self.assertEqual(timer.call_count,6)
        self.assertEqual(subject.overlay.hide.call_count,6)

