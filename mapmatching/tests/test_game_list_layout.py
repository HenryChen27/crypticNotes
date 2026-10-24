import os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6 import QtWidgets as W,QtCore as C
from mapmatching.theme import install_font
import mapmatching.minigames_ui as ui

class GameListLayoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=W.QApplication.instance() or W.QApplication([]);cls.family=install_font(cls.app)[0]
 def make_controls(self,root):
  specs={}
  for id,name in [('jellyfish','合成大水母'),('minesweeper','蚀骨赠礼')]:
   folder=root/'minigames'/id;(folder/'game').mkdir(parents=True);(folder/'game/index.html').write_text('<html/>');(folder/'package.json').write_text(json.dumps(dict(id=id,version='1.0.0',runtime='system-webview')))
   specs[id]=dict(id=id,name=name,version='1.0.0',size=25*1048576,sha256='0'*64)
  runtime=root/'minigames/runtime';runtime.mkdir();(runtime/'GameLauncher.exe').write_bytes(b'launcher');(runtime/'package.json').write_text(json.dumps(dict(version='2.5.3')))
  cache=root/'out/minigames/catalog.json';cache.parent.mkdir(parents=True);cache.write_text(json.dumps(dict(games=specs)))
  parent=W.QWidget();parent.resize_settings=lambda:None;layout=W.QVBoxLayout(parent)
  controls=ui.GameControls(parent);layout.addWidget(controls);parent.setFixedWidth(350);parent.show();self.app.processEvents()
  return parent,controls
 def test_caption_matches_requested_compact_format(self):
  self.assertEqual(ui.compact_game_caption('1.0.0',25*1048576),'v1.0.0 · 25MB')
  self.assertEqual(ui.compact_game_caption('v2.5.2',int(17.5*1048576)),'v2.5.2 · 17.5MB')
 def test_launch_remains_in_bounds_after_repeated_refresh(self):
  with tempfile.TemporaryDirectory() as d,patch.object(ui,'DATA_ROOT',Path(d)),patch.object(ui.GameControls,'sync_catalog',lambda _:None),patch('mapmatching.local_minigames.local_games',return_value=[]):
   parent,controls=self.make_controls(Path(d))
   try:
    for _ in range(4):controls.refresh();self.app.processEvents()
    for card in controls.game_cards:
     self.assertTrue(card.launch.isVisible());self.assertTrue(card.launch.isEnabled())
     self.assertLessEqual(card.launch.geometry().right(),card.width())
     self.assertEqual(card.subtitle.text(),'v1.0.0 · 25MB')
     self.assertNotIn('\n',card.title.text())
    self.assertTrue(controls.status.isHidden())
    Path('out').mkdir(exist_ok=True);parent.setStyleSheet('QWidget{background:#243847;color:#dbe4e9;font-family:"'+self.family+'";font-size:18px;}');self.app.processEvents();parent.grab().save('out/game-list-layout-preview.png')
   finally:parent.close();parent.deleteLater();self.app.processEvents()
 def test_management_button_does_not_reparent_when_game_removed(self):
  with tempfile.TemporaryDirectory() as d,patch.object(ui,'DATA_ROOT',Path(d)),patch.object(ui.GameControls,'sync_catalog',lambda _:None),patch('mapmatching.local_minigames.local_games',return_value=[]):
   parent,controls=self.make_controls(Path(d))
   try:
    download=controls.game_rows[0][1];original_parent=download.parentWidget()
    (Path(d)/'minigames/jellyfish/game/index.html').unlink();controls.refresh();self.app.processEvents()
    self.assertIs(download.parentWidget(),original_parent)
    self.assertTrue(controls.game_cards[0].download.isVisible());self.assertFalse(controls.game_cards[0].launch.isVisible())
   finally:parent.close();parent.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()
