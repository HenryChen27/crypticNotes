"""Closing the map must not kill the matching worker; a queued frame goes next.

Friend's log (datasets/evaluation/20261109-friend-records): closing while a
match ran killed the worker 475 times, so the next open always waited 1-2 s
for a restart and, on weak frames, never saw a result.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mapmatching.src.live import ToggleState


def subject():
    state = ToggleState(); state.open()
    return SimpleNamespace(state=state, overlay=Mock(), toast=Mock(), pending=None,
        restore_capture_companion=Mock(), gear=Mock(), busy=True, process=Mock(), ready=True,
        stop_worker=Mock(), start_worker=Mock(), notify=Mock(), dismiss_manual_offer=Mock(),
        keys=SimpleNamespace(edges=lambda: set(), hide_key=8, toggle_key=71), enabled=Mock(),
        is_game=lambda _: False, connection=Mock(), worker_deadline=None, cached_candidate=None,
        request_token=state.generation, request_started=100.0)


class WorkerReuseTests(unittest.TestCase):
    def test_close_while_matching_keeps_worker(self):
        from mapmatching.ui import Companion
        s = subject()
        Companion.close_map(s, silent=True)
        s.stop_worker.assert_not_called()

    def test_queued_frame_is_sent_when_old_result_arrives(self):
        from mapmatching.ui import Companion, W, win32gui
        s = subject(); old = s.state.generation
        Companion.close_map(s, silent=True)
        # Frame of the next open, queued behind the old request (the state is
        # left closed so this tick skips the foreground checks).
        s.pending = (old + 1, object(), None, {})
        s.connection.poll.return_value = True
        s.connection.recv.return_value = ('result', (old, None, 'old', None, 10, {}))
        with patch.object(W.QApplication, 'activeModalWidget', return_value=None), \
                patch.object(win32gui, 'GetForegroundWindow', return_value=42):
            Companion.tick(s)
        s.overlay.display.assert_not_called()
        s.start_worker.assert_called_once()

    def test_long_stale_request_restarts_worker_and_keeps_new_frame(self):
        from mapmatching.ui import Companion, STALE_REQUEST_S
        s = subject()
        Companion.close_map(s, silent=True)
        new = s.state.open(); frame = (new, object(), None, {})
        s.pending = frame
        s.stop_worker = Mock(side_effect=lambda: setattr(s, 'pending', None))
        with patch('mapmatching.ui.time.monotonic', return_value=100.0 + STALE_REQUEST_S / 2):
            self.assertFalse(Companion.restart_stale_worker(s))
        with patch('mapmatching.ui.time.monotonic', return_value=100.0 + STALE_REQUEST_S + .1):
            self.assertTrue(Companion.restart_stale_worker(s))
        s.stop_worker.assert_called_once()
        self.assertIs(s.pending, frame)
        s.start_worker.assert_called_once()

    def test_current_request_is_never_restarted(self):
        from mapmatching.ui import Companion, STALE_REQUEST_S
        s = subject(); s.pending = (s.state.generation, object(), None, {})
        with patch('mapmatching.ui.time.monotonic', return_value=100.0 + 10 * STALE_REQUEST_S):
            self.assertFalse(Companion.restart_stale_worker(s))
        s.stop_worker.assert_not_called()


class SingleViewTests(unittest.TestCase):
    """磷光症 with a read floor: one cropped pass, no wider retries."""

    def matcher(self, single):
        from mapmatching.src.matcher import MapMatcher, MatchResult
        m = MapMatcher.__new__(MapMatcher)
        m.floor_hint, m.single_view, m.floor_references = -3, single, []
        m._match_view = Mock(return_value=MatchResult())
        return m

    def test_match_stops_after_first_pass(self):
        with patch('mapmatching.src.phone_layout.phone_viewport', return_value=None):
            m = self.matcher(True); result = m.match(object())
            self.assertEqual(m._match_view.call_count, 1)
            self.assertTrue(result.diagnostics.get('single_view'))
            m = self.matcher(False); m.match(object())
            self.assertEqual(m._match_view.call_count, 3)

    def test_match_with_cache_sets_single_view_only_for_basement_reading(self):
        from mapmatching.src import live
        from mapmatching.src.matcher import MatchResult
        m = SimpleNamespace(floor_hint=None, single_view=None, match=Mock(return_value=MatchResult()))
        basement = lambda px: dict(floor=-3, reader='basement', buttons=[], bbox=None)
        with patch.object(live, 'library_floors', return_value={-1, -2, -3}), \
                patch('mapmatching.src.floor_tabs.hide_floor_column', side_effect=lambda px, r: px), \
                patch('mapmatching.src.floor_tabs.inspect_basement_tabs', basement):
            live.match_with_cache(m, object(), floor_tabs=basement)
        self.assertTrue(m.single_view)
        live.match_with_cache(m, object(), floor_tabs=lambda px: dict(floor=2, reader='standard'))
        self.assertFalse(m.single_view)


if __name__ == '__main__':
    unittest.main()
