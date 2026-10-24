import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6 import QtWidgets as W,QtGui as G
from mapmatching.game_icons import game_pixmap,game_icon_candidates,cache_catalog_icons
from unittest.mock import patch
import io,hashlib

class GameIconTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
 def test_package_convention_wins_over_legacy_icon(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);path=folder/'game/assets/icon.png';path.parent.mkdir(parents=True)
   image=G.QImage(500,250,G.QImage.Format_ARGB32);image.fill(G.QColor('red'));image.save(str(path))
   store=SimpleNamespace(folder=folder,game_id='jellyfish',icon=Path('old-spider.png'))
   self.assertEqual(next(game_icon_candidates(store)),path)
   pixmap=game_pixmap(store);self.assertEqual((pixmap.width(),pixmap.height()),(96,48));self.assertEqual(pixmap.toImage().pixelColor(20,20),G.QColor('red'))
 def test_corrupt_and_missing_icons_have_nonempty_fallback(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);path=folder/'game/assets/icon.png';path.parent.mkdir(parents=True);path.write_bytes(b'broken')
   for id in ('jellyfish','minesweeper','mini-kitchen','future-game'):
    self.assertFalse(game_pixmap(SimpleNamespace(folder=folder,game_id=id)).isNull())
 def test_local_source_uses_same_convention(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);store=SimpleNamespace(folder=folder,game_root=folder,game_id='minesweeper')
   self.assertEqual(next(game_icon_candidates(store)),folder/'assets/icon.png')
 def test_new_game_catalog_icon_is_cached_before_install(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);image=G.QImage(64,64,G.QImage.Format_ARGB32);image.fill(G.QColor('green'));source=folder/'source.png';image.save(str(source));data=source.read_bytes()
   spec={'games':{'future-game':{'icon':{'url':'https://github.com/HenryChen27/mini_games/releases/download/test/future-game-icon.png','sha256':hashlib.sha256(data).hexdigest()}}}}
   with patch('mapmatching.game_icons.DATA_ROOT',folder),patch('urllib.request.urlopen',return_value=io.BytesIO(data)):
    cache_catalog_icons(spec)
    pixmap=game_pixmap(SimpleNamespace(folder=folder/'not-installed',game_id='future-game'))
    self.assertEqual(pixmap.toImage().pixelColor(2,2),G.QColor('green'))
 def test_remote_icon_hash_failure_does_not_block_catalog(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);spec={'games':{'future-game':{'icon':{'url':'https://github.com/HenryChen27/mini_games/releases/download/test/icon.png','sha256':'0'*64}}}}
   with patch('mapmatching.game_icons.DATA_ROOT',folder),patch('urllib.request.urlopen',return_value=io.BytesIO(b'invalid')):
    cache_catalog_icons(spec)
   self.assertFalse((folder/'out/minigames/icons/future-game.png').exists())
 def test_replaced_package_icon_is_reloaded(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);path=folder/'game/assets/icon.png';path.parent.mkdir(parents=True);store=SimpleNamespace(folder=folder,game_id='jellyfish')
   for color in ('red','blue'):
    image=G.QImage(32,32,G.QImage.Format_ARGB32);image.fill(G.QColor(color));image.save(str(path))
    self.assertEqual(game_pixmap(store).toImage().pixelColor(2,2),G.QColor(color))
if __name__=='__main__':unittest.main()
