"""Companion feedback must preserve fonts and survive capture cancellation."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6 import QtWidgets as W, QtGui as G
from mapmatching.ui import Companion, font_stack, FONT_CACHE
from mapmatching.src.live import ToggleState


class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=W.QApplication.instance() or W.QApplication([])

    def test_loading_fonts_does_not_reset_selected_application_font(self):
        original=self.app.font()
        selected=G.QFont('Microsoft YaHei UI'); selected.setPixelSize(19)
        cached=FONT_CACHE[:]
        try:
            self.app.setFont(selected)
            FONT_CACHE.clear()
            font_stack('system')
            self.assertEqual(self.app.font(),selected)
        finally:
            FONT_CACHE[:]=cached
            self.app.setFont(original)

    def test_update_reports_start_immediately_then_window_ready(self):
        subject=W.QWidget()
        subject.save=Mock();subject.notify=Mock();subject.status=Mock()
        subject.update_button=W.QPushButton('check',subject)
        selected=self.app.font()
        with tempfile.TemporaryDirectory() as folder, \
             patch('mapmatching.paths.FROZEN',True), \
             patch('tempfile.gettempdir',return_value=folder), \
             patch('subprocess.Popen') as launch:
            Companion.check_update(subject)
            self.assertFalse(subject.update_button.isEnabled())
            subject.notify.assert_called_once()
            args=launch.call_args.args[0]
            marker=Path(args[args.index('-ReadyFile')+1])
            marker.write_text('ready')
            deadline=time.monotonic()+2
            while not subject.update_button.isEnabled() and time.monotonic()<deadline:
                self.app.processEvents();time.sleep(.01)
            self.assertTrue(subject.update_button.isEnabled())
            self.assertFalse(marker.exists())
            self.assertEqual(self.app.font(),selected)
        subject.deleteLater()

    def test_updater_start_blocks_settings_and_duplicate_launch(self):
        subject=SimpleNamespace(_update_starting=True,notify=Mock(),toast=Mock())
        with patch('subprocess.Popen') as launch:
            Companion.toggle_panel(subject)
            Companion.check_update(subject)
        launch.assert_not_called()
        subject.toast.hide.assert_not_called()
        self.assertEqual(subject.notify.call_count,2)

    def test_open_updater_process_is_not_launched_twice(self):
        process=Mock();process.poll.return_value=None
        subject=SimpleNamespace(_updater_process=process,notify=Mock())
        with patch('subprocess.Popen') as launch:
            Companion.check_update(subject)
        launch.assert_not_called()
        subject.notify.assert_called_once()

    def test_close_restores_hidden_companion_and_ends_feedback(self):
        state=ToggleState();state.open()
        subject=SimpleNamespace(state=state,_capture_hidden=True,gear=Mock(),overlay=Mock(),toast=Mock(),
            process=None,busy=False,pending=None,notify=Mock(),show=Mock(),winId=lambda:42)
        subject.restore_capture_companion=lambda:Companion.restore_capture_companion(subject)
        with patch('mapmatching.ui.show_floating') as show:
            Companion.close_map(subject,silent=True)
        show.assert_called_once_with(subject)
        self.assertFalse(subject._capture_hidden)
        self.assertFalse(state.opened)
        subject.gear.set_matching.assert_called_with(False)

    def test_obstructed_visibility_requires_clean_confirmation(self):
        import queue
        subject=SimpleNamespace(state=ToggleState(),visibility_results=queue.SimpleQueue(),
            visibility_running=False,visibility_next=float('inf'),visibility_misses=1,
            visibility_token=None,isVisible=lambda:True,close_map=Mock(),
            demo_window=None,opening=False,capture_rect=lambda:(0,0,1000,600),hide=Mock())
        token=subject.state.open();subject.visibility_token=token
        subject.visibility_results.put((token,False))
        with patch('mapmatching.ui.C.QTimer.singleShot'):
            Companion.visibility_watch(subject)
        subject.close_map.assert_not_called()
        self.assertTrue(subject._visibility_hidden)
        subject.visibility_results.put((token,True))
        with patch('mapmatching.ui.show_floating'):
            Companion.visibility_watch(subject)
        self.assertTrue(subject.visibility_obstructed)
        self.assertFalse(subject._visibility_hidden)
        subject.close_map.assert_not_called()
