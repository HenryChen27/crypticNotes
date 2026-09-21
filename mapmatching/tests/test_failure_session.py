import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mapmatching.src.live import ToggleState


class FailureSessionTests(unittest.TestCase):
    def test_rejected_scene_stops_following_and_keeps_identity(self):
        from mapmatching.ui import Companion, W, win32gui
        state=ToggleState();token=state.open()
        cached=object()
        details={'candidates':[], 'diagnostics':{'anchors':300,'foreground_pixels':100000}}
        s=SimpleNamespace(state=state,keys=SimpleNamespace(edges=lambda:set()),
            enabled=SimpleNamespace(isChecked=lambda:False), target=42,
            winId=lambda:43,foreground_lost=lambda:False,rect_at_capture=None,
            follow=Mock(), connection=Mock(), busy=True, started=0,
            follow_active=False,follow_dirty=False,mouse_busy=lambda:False,
            cached_candidate=cached,notify=Mock())
        s.connection.poll.return_value=True
        s.connection.recv.return_value=('result',(token,None,'匹配证据不足',None,100,details))
        s.close_map=Mock(side_effect=lambda **kw:state.close())
        with patch.object(W.QApplication,'activeModalWidget',return_value=None), patch.object(win32gui,'GetForegroundWindow',return_value=42),patch('mapmatching.ui.no_map_evidence',return_value=False):
            Companion.tick(s)
            s.close_map.assert_called_once_with(silent=True)
            self.assertFalse(state.opened)
            self.assertIs(s.cached_candidate,cached)
            s.follow.reset_mock();s.connection=None
            Companion.tick(s)
            s.follow.assert_not_called()
