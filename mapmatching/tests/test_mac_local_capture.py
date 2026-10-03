"""Mac-only capture routing and worker warm-up regressions."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from mapmatching.src.live import ToggleState


class MacCaptureTests(unittest.TestCase):
    def test_local_image_uses_original_without_screen_capture_or_mask(self):
        from mapmatching.ui import Companion,native
        state=ToggleState();token=state.open()
        pixels=np.zeros((90,160,3),dtype=np.uint8)
        subject=SimpleNamespace(state=state,foreground_lost=lambda:False,
            capture_rect=lambda:(10,20,320,180),demo_window=object(),demo=Path('fixture.png'),
            isVisible=lambda:True,cached_candidate=None,opening=True,
            record_failures=Mock(),records_directory=lambda:Path('out'),status=Mock(),
            start_worker=Mock(),close_map=Mock(),notify=Mock())
        with patch('mapmatching.ui.sys.platform','darwin'),patch('mapmatching.src.reference.read_image',return_value=pixels) as read,patch.object(native,'capture') as capture,patch.object(native,'mask_screen_rect') as mask:
            Companion.capture_after_hide(subject,token)
        read.assert_called_once_with(subject.demo)
        capture.assert_not_called();mask.assert_not_called()
        self.assertIs(subject.pending[1],pixels)
        self.assertEqual(subject.pending[3]['source'],'local_screenshot')
        subject.start_worker.assert_called_once()
        subject.notify.assert_not_called()

    def test_mac_keeps_idle_initializing_worker_windows_keeps_original_behavior(self):
        from mapmatching.ui import Companion
        for platform,stops in [('darwin',0),('win32',1)]:
            subject=SimpleNamespace(state=ToggleState(),overlay=Mock(),toast=Mock(),
                busy=False,process=object(),ready=False,stop_worker=Mock(),notify=Mock())
            with patch('mapmatching.ui.sys.platform',platform):
                Companion.close_map(subject,silent=True)
            self.assertEqual(subject.stop_worker.call_count,stops)


if __name__=='__main__': unittest.main()
