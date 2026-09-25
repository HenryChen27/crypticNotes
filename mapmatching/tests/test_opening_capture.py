import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from mapmatching.src.live import ToggleState
from mapmatching.src.windows import Keys


class OpeningCaptureTests(unittest.TestCase):
    def test_short_press_survives_release_before_poll_and_repeat(self):
        keys=Keys();keys.raw_active=True
        with patch('mapmatching.src.windows.user32.GetAsyncKeyState',return_value=0):
            keys.raw_edge(71,False);keys.raw_edge(71,False);keys.raw_edge(71,True)
            self.assertEqual(keys.edges(),{71})
            self.assertEqual(keys.edges(),set())
            keys.raw_edge(71,False)
            self.assertEqual(keys.edges(),{71})
            keys.raw_edge(71,False)
            self.assertEqual(keys.edges(),set())

    def test_mouse_cannot_replace_initial_delayed_capture(self):
        from mapmatching.ui import Companion
        s=SimpleNamespace(opening=True)
        Companion.follow(s) # Must return before touching mouse or generation.

    def test_opening_retries_then_captures_and_escape_cancels_retry(self):
        from mapmatching.ui import Companion,C,native
        state=ToggleState();token=state.open();callbacks=[]
        s=SimpleNamespace(state=state,opening=True,open_probe_count=0,demo_window=None,
            foreground_lost=lambda:False,capture_rect=lambda:(0,0,2560,1600),
            show=Mock(),take_capture=Mock(),start_worker=Mock(),cached_candidate=None,
            record_failures=SimpleNamespace(isChecked=lambda:True),status=Mock(),
            records_directory=lambda:'test-records')
        with patch.object(native,'capture',return_value=np.zeros((10,10,3),np.uint8)),patch.object(C.QTimer,'singleShot',side_effect=lambda ms,fn:callbacks.append(fn)),patch('mapmatching.src.map_visibility.inspect_map_ui',return_value={'visible':False}):
            Companion.capture_after_hide(s,token)
            self.assertEqual(s.open_probe_count,1)
            s.start_worker.assert_not_called()
            state.close();callbacks.pop()()
            s.take_capture.assert_not_called()
            token=state.open()
            s.open_probe_count=5
            Companion.capture_after_hide(s,token)
            self.assertFalse(s.opening)
            s.start_worker.assert_called_once()
            self.assertEqual(s.pending[3]['records_directory'], 'test-records')
