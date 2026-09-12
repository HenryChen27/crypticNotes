"""Input synchronization regression without real keyboard input or desktop capture."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from mapmatching.src.live import ToggleState


class SyncTests(unittest.TestCase):
    def subject(self,opened,local=False):
        state=ToggleState(opened=opened)
        subject=SimpleNamespace(state=state,keys=SimpleNamespace(toggle_key=71,edges=lambda:{71}),
            enabled=SimpleNamespace(isChecked=lambda:True),demo_window=object() if local else None,
            connection=None,is_game=lambda _:True)
        subject.open_map=Mock(side_effect=state.close)
        subject.close_map=Mock(side_effect=state.close)
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
