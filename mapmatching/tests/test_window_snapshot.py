import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from mapmatching import window_map_capture as capture


class SnapshotTests(unittest.TestCase):
    def test_only_first_frame_is_copied_before_native_stop_finishes(self):
        self.check_frames(False)

    def test_cancelled_snapshot_does_not_copy_a_late_frame(self):
        self.check_frames(True)

    def check_frames(self,cancelled):
        control=Mock()
        class Native:
            def __init__(self,**kwargs):self.handlers={}
            def event(self,callback):self.handlers[callback.__name__]=callback;return callback
            def start_free_threaded(self):return control
        module=SimpleNamespace(WindowsCapture=Native)
        with patch.dict('sys.modules',windows_capture=module),patch.object(capture,'_capture_slots',Mock()),patch.object(capture.threading,'Thread'),patch.object(capture,'frame_rect',return_value=(0,0,200,100)),patch.object(capture,'normalize_frame',return_value=np.zeros((100,200,3),dtype=np.uint8)) as normalize:
            shot=capture.WindowSnapshot(123)
            if cancelled:shot.stop()
            callback=shot.capture.handlers['on_frame_arrived']
            for _ in range(20):callback(SimpleNamespace(frame_buffer=object()),control)
            self.assertEqual(normalize.call_count,0 if cancelled else 1)
            self.assertEqual(control.stop.call_count,0 if cancelled else 1)
            self.assertEqual(shot.result is None,cancelled)


if __name__=='__main__':unittest.main()
