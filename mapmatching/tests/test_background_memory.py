import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from mapmatching.src.live import ToggleState


class BackgroundMemoryTests(unittest.TestCase):
    def test_custom_close_key_closes_even_with_shortcuts_disabled(self):
        from mapmatching.ui import Companion,W,win32gui
        for key in (2,5,6,20,13,8,27):
            s=self.subject();s.keys.close_key=key;s.keys.edges=lambda:{key}
            s.enabled.isChecked.return_value=False
            s.close_map=Mock(side_effect=lambda **kw:setattr(s.state,'opened',False))
            s.connection.poll.return_value=False
            with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
                Companion.tick(s)
                Companion.tick(s)
            self.assertEqual(s.close_map.call_count,2)
            s.close_map.assert_called_with(background=True)

    def test_visibility_fallback_requires_two_current_negative_frames(self):
        import queue
        from mapmatching.ui import Companion
        s=self.subject();s.close_map=Mock()
        s.visibility_results=queue.SimpleQueue();s.visibility_running=False
        s.visibility_next=float('inf');s.visibility_misses=0;s.visibility_token=None
        token=s.state.generation
        s.visibility_results.put((token-1,False))
        Companion.visibility_watch(s)
        self.assertEqual(s.visibility_misses,0)
        for n in (1,2):
            s.visibility_results.put((token,False))
            Companion.visibility_watch(s)
            self.assertEqual(s.close_map.call_count,n-1)

    def subject(self):
        state=ToggleState();state.open()
        return SimpleNamespace(state=state,overlay=Mock(),toast=Mock(),pending=None,
            busy=True,process=Mock(),ready=True,stop_worker=Mock(),notify=Mock(),
            keys=SimpleNamespace(edges=lambda:set(),hide_key=8,toggle_key=71),enabled=Mock(),
            is_game=lambda _:False,connection=Mock(),worker_deadline=None,
            cached_candidate=None)

    def test_closed_result_remembers_without_display_or_notification(self):
        from mapmatching.ui import Companion,W,win32gui
        s=self.subject();token=s.state.generation
        Companion.close_map(s,silent=True,background=True)
        s.stop_worker.assert_not_called()
        c=SimpleNamespace(map_id='test')
        s.connection.poll.return_value=True
        s.connection.recv.return_value=('result',(token,object(),'ok',c,10,{}))
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42),patch('mapmatching.ui.no_map_evidence',return_value=False):
            Companion.tick(s)
        self.assertIs(s.cached_candidate,c)
        s.overlay.display.assert_not_called()
        s.notify.assert_not_called()

    def test_superseding_close_discards_old_proposal(self):
        from mapmatching.ui import Companion,W,win32gui
        s=self.subject();token=s.state.generation
        Companion.close_map(s,silent=True,background=True)
        Companion.close_map(s,silent=True) # open_map/context change cancels
        s.stop_worker.assert_called_once()
        s.connection.poll.return_value=True
        s.connection.recv.return_value=('result',(token,object(),'ok',object(),10,{}))
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
            Companion.tick(s)
        self.assertIsNone(s.cached_candidate)
        s.overlay.display.assert_not_called()

    def test_captured_pending_request_survives_close(self):
        from mapmatching.ui import Companion
        s=self.subject();pending=object();s.pending=pending
        Companion.close_map(s,silent=True,background=True)
        self.assertIs(s.pending,pending)
