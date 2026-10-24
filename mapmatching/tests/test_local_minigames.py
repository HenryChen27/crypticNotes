import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from mapmatching.local_minigames import LocalGameStore,local_games
from mapmatching.minigames_ui import GameControls,game_profile

class LocalGamesTests(unittest.TestCase):
    def test_packaged_app_never_reads_local_registrations(self):
        with patch('mapmatching.local_minigames.FROZEN',True):
            self.assertEqual(local_games(Path('nonexistent')),[])

    def test_local_source_is_direct_and_save_profiles_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();(source/'index.html').write_text('source')
            store=LocalGameStore(root,{'id':'minesweeper','title':'test','source':str(source)})
            store.entry().parent.mkdir(parents=True);store.entry().touch()
            self.assertTrue(store.installed());self.assertEqual(store.game_root,source.resolve())
            with patch('mapmatching.minigames_ui.DATA_ROOT',root):
                self.assertNotEqual(game_profile(SimpleNamespace(store=store)),game_profile(SimpleNamespace()))

    def test_switch_running_game_requests_safe_close_without_second_launch(self):
        first,second=object(),object()
        subject=SimpleNamespace(task=None,running=lambda:True,store=first,stores=[first,second],
            game_choice=Mock(),status=Mock(),send_window_command=Mock(),process=Mock(),cancel_game_switch=Mock())
        with patch('mapmatching.minigames_ui.C.QTimer.singleShot'):
            GameControls.select_game(subject,1)
        self.assertIs(subject.store,first)
        self.assertEqual(subject.pending_game_index,1)
        subject.send_window_command.assert_called_once_with('safe-close')
        subject.process.start.assert_not_called()

    def test_failed_save_keeps_old_game_and_cancels_switch(self):
        first,second=object(),object()
        subject=SimpleNamespace(pending_game_index=1,running=lambda:True,store=first,stores=[first,second],
            game_choice=Mock(),status=Mock(),refresh=Mock())
        GameControls.cancel_game_switch(subject)
        self.assertIsNone(subject.pending_game_index)
        self.assertIs(subject.store,first)

if __name__=='__main__':unittest.main()
