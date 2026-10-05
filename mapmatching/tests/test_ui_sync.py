"""Input synchronization regression without real keyboard input or desktop capture."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from mapmatching.src.live import ToggleState


class SyncTests(unittest.TestCase):
    def test_hung_worker_is_released_and_user_is_notified(self):
        from mapmatching.ui import Companion,W,win32gui
        subject=self.subject(False)
        subject.keys.edges=lambda:set()
        subject.connection=Mock()
        subject.connection.poll.return_value=False
        subject.worker_deadline=10
        subject.busy=True
        subject.ready=True
        subject.stop_worker=Mock()
        subject.notify=Mock()
        subject.close_map=Mock()
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42),patch('mapmatching.ui.time.monotonic',return_value=11):
            Companion.tick(subject)
        subject.stop_worker.assert_called_once()
        subject.notify.assert_called_once()

    def test_retry_collapses_settings_before_capture(self):
        from mapmatching.ui import Companion,C,native
        subject=SimpleNamespace(panel=Mock(),toggle_panel=Mock(),cached_candidate=object(),
            demo=None,last_external_target=42,open_map=Mock())
        subject.panel.isVisible.return_value=True
        callbacks=[]
        with patch.object(native,'activate_target',create=True) as activate,patch.object(C.QTimer,'singleShot',side_effect=lambda ms,fn:callbacks.append(fn)):
            Companion.retry(subject)
            subject.toggle_panel.assert_called_once()
            activate.assert_called_once_with(42)
            self.assertIsNone(subject.cached_candidate)
            callbacks[0]()
            subject.open_map.assert_called_once_with('manual_retry')

    def test_mac_focus_handoff_does_not_cancel_manual_retry(self):
        from mapmatching.ui import Companion,W,win32gui
        state=ToggleState();state.open()
        subject=SimpleNamespace(state=state,keys=SimpleNamespace(edges=lambda:set()),
            enabled=SimpleNamespace(isChecked=lambda:False),target=43,winId=lambda:43,
            is_game=lambda target:target==42,foreground_lost=lambda:False,
            rect_at_capture=None,follow=Mock(),connection=None,close_map=Mock())
        with patch('mapmatching.ui.sys.platform','darwin'),patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
            Companion.tick(subject)
        self.assertEqual(subject.target,42)
        subject.close_map.assert_not_called()
        subject.follow.assert_called_once()

    def test_sparse_cached_alignment_can_reposition_but_not_identify(self):
        from mapmatching.src.live import cached_alignment_candidate,presentation_candidate
        from mapmatching.src.matcher import MatchResult
        from mapmatching.src.types import Candidate,Pose
        candidate=Candidate('hard/test','hard',None,2,Pose(1,10,20),.58,.32,1)
        result=MatchResult(candidates=[candidate])
        self.assertIsNone(presentation_candidate(result)[0])
        self.assertIs(cached_alignment_candidate(result)[0],candidate)

    def test_blank_floor_keeps_session_and_return_can_overlay(self):
        from mapmatching.ui import Companion,W,win32gui,no_map_evidence
        from mapmatching.src.types import Candidate,Pose
        import time
        state=ToggleState(); token=state.open()
        candidate=Candidate('hard/test','hard',None,10,Pose(1,0,0),.9,.1,1)
        subject=Mock()
        subject.worker_deadline=None
        subject.state=state
        subject.keys.edges.return_value=set()
        subject.enabled.isChecked.return_value=False
        subject.foreground_lost.return_value=False
        subject.target=42
        subject.winId.return_value=43
        subject.opacity.value.return_value=30
        subject.rect_at_capture=None
        subject.connection.poll.return_value=True
        subject.mouse_busy.return_value=False
        subject.follow_active=subject.follow_dirty=False
        subject.cached_candidate=None
        subject.started=time.perf_counter()
        subject.close_map=Mock(side_effect=lambda **kwargs:state.close())
        visible={'diagnostics':{'map_ui':{'visible':True},'anchors':400},'candidates':[]}
        self.assertFalse(no_map_evidence(visible))
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
            for layer,current in ((object(),candidate),(None,None),(object(),candidate)):
                subject.connection.recv.return_value=('result',(token,layer,'ambiguous',current,1,visible))
                Companion.tick(subject)
                self.assertTrue(state.opened)
                self.assertIs(subject.cached_candidate,candidate)
        subject.close_map.assert_not_called()
        self.assertEqual(subject.overlay.display.call_count,2)
        subject.overlay.hide.assert_called_once()

    def subject(self,opened,local=False):
        state=ToggleState(opened=opened)
        subject=SimpleNamespace(state=state,keys=SimpleNamespace(toggle_key=71,hide_key=8,edges=lambda:{71}),
            enabled=SimpleNamespace(isChecked=lambda:True),demo_window=object() if local else None,
            connection=None,is_game=lambda _:True,target=42,winId=lambda:43)
        subject.open_map=Mock(side_effect=state.close)
        subject.close_map=Mock(side_effect=lambda **kwargs:state.close())
        return subject

    def test_g_resamples_game_even_when_old_state_is_open(self):
        from mapmatching.ui import Companion,W,win32gui
        for opened in (True,False):
            subject=self.subject(opened)
            with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
                Companion.tick(subject)
            subject.open_map.assert_called_once()
            subject.close_map.assert_not_called()

    def test_static_local_overlay_still_toggles(self):
        from mapmatching.ui import Companion,W,win32gui
        subject=self.subject(True,local=True)
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
            Companion.tick(subject)
        subject.close_map.assert_called_once()
        subject.open_map.assert_not_called()

    def test_escape_clears_even_already_closed_state(self):
        from mapmatching.ui import Companion,W,win32gui
        subject=self.subject(False); subject.keys.edges=lambda:{27}
        with patch.object(W.QApplication,'activeModalWidget',return_value=None),patch.object(win32gui,'GetForegroundWindow',return_value=42):
            Companion.tick(subject)
        subject.close_map.assert_called_once()

    def test_confirmation_is_automatic_but_cannot_resurrect_after_escape(self):
        from mapmatching.ui import Companion,W
        state=ToggleState(); token=state.open()
        subject=SimpleNamespace(state=state,mouse_busy=lambda:False,busy=False,_capturing=False,realign=Mock())
        with patch.object(W.QApplication,'activeModalWidget',return_value=None):
            Companion.confirm_map_closed(subject,token)
            subject.realign.assert_called_once()
            state.close()
            Companion.confirm_map_closed(subject,token)
            subject.realign.assert_called_once()

