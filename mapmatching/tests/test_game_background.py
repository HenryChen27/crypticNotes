import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from mapmatching.minigames_ui import GameControls
from mapmatching.ui import Companion


class GameBackgroundTests(unittest.TestCase):
    def test_running_game_blocks_capture_and_retry_restores_instead(self):
        games=SimpleNamespace(running=lambda:True,game_hidden=True,restore_game=Mock())
        subject=SimpleNamespace(minigames=games)
        # No capture or matcher dependencies exist: these must return early.
        Companion.open_map(subject)
        Companion.take_capture(subject,1)
        Companion.retry(subject)
        games.restore_game.assert_called_once()

    def test_hidden_state_and_restore_command_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory,patch('mapmatching.minigames_ui.DATA_ROOT',Path(directory)):
            profile=Path(directory)/'minigame-saves/jellyfish';profile.mkdir(parents=True)
            gear=Mock();subject=SimpleNamespace(running=lambda:True,game_hidden=False,companion=SimpleNamespace(gear=gear))
            (profile/'window-state.json').write_text('{"hidden":true}')
            GameControls.check_window_state(subject)
            self.assertTrue(subject.game_hidden);gear.set_game_background.assert_called_with(True)
            self.assertTrue(GameControls.restore_game(subject))
            first=json.loads((profile/'window-command.json').read_text())
            GameControls.restore_game(subject)
            second=json.loads((profile/'window-command.json').read_text())
            self.assertEqual(second['action'],'show');self.assertNotEqual(first['id'],second['id'])
            (profile/'window-state.json').write_text('{"hidden":false}')
            GameControls.check_window_state(subject)
            self.assertFalse(subject.game_hidden);gear.set_game_background.assert_called_with(False)

if __name__=='__main__':unittest.main()
