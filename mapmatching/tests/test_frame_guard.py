import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import numpy as np
from mapmatching.src.frame_guard import unchanged_map
from mapmatching.mouse_input import MouseWatcher


class FrameGuardTests(unittest.TestCase):
    def test_dirty_success_is_displayed_when_current_map_is_unchanged(self):
        from mapmatching.ui import Companion,W,win32gui,native
        from mapmatching.src.live import ToggleState
        state=ToggleState();token=state.open()
        pixels=np.zeros((10,10,3),np.uint8)
        candidate=SimpleNamespace(map_id='hard/test',floor=1)
        s=SimpleNamespace(state=state,keys=SimpleNamespace(edges=lambda:set()),
            enabled=SimpleNamespace(isChecked=lambda:False),target=42,winId=lambda:43,
            foreground_lost=lambda:False,rect_at_capture=None,follow=Mock(),
            connection=Mock(),busy=True,started=0,follow_active=False,follow_dirty=True,
            mouse_busy=lambda:False,request_pixels=pixels,capture_rect=lambda:(0,0,10,10),
            overlay=Mock(),opacity=SimpleNamespace(value=lambda:30),notify=Mock())
        s.connection.poll.return_value=True
        s.connection.recv.return_value=('result',(token,pixels,'ok',candidate,10,{}))
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42),patch.object(native,'capture',return_value=pixels),patch('mapmatching.src.frame_guard.unchanged_map',return_value=(True,{'reason':'test'})),patch('mapmatching.ui.no_map_evidence',return_value=False):
            Companion.tick(s)
        s.overlay.display.assert_called_once()
        self.assertFalse(s.follow_dirty)
        self.assertIs(s.cached_candidate,candidate)

    def test_same_frame_reused_but_translation_rejected(self):
        image=np.zeros((600,960,3),np.uint8)
        image[180:400,400:600]=150
        with patch('mapmatching.src.frame_guard.inspect_map_ui',return_value={'visible':True}):
            self.assertTrue(unchanged_map(image,image.copy())[0])
            self.assertFalse(unchanged_map(image,np.roll(image,12,axis=1))[0])

    def test_closed_map_never_reused_even_if_pixels_equal(self):
        image=np.zeros((600,960,3),np.uint8)
        with patch('mapmatching.src.frame_guard.inspect_map_ui',return_value={'visible':False}):
            self.assertFalse(unchanged_map(image,image)[0])

    def test_only_left_button_or_wheel_invalidates_map(self):
        watcher=MouseWatcher()
        with patch.object(watcher,'interacting'),patch('mapmatching.mouse_input.time.perf_counter',return_value=10):
            watcher.buttons={2,4,5,6}
            self.assertFalse(watcher.map_interacting())
            watcher.buttons.add(1)
            self.assertTrue(watcher.map_interacting())
            watcher.buttons.clear();watcher.last_wheel=9.99
            self.assertTrue(watcher.map_interacting())
