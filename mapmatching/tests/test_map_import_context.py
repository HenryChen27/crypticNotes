import tempfile,unittest
from pathlib import Path
from PySide6 import QtWidgets as W
from mapmatching.map_import_ui import MapImportDialog
from mapmatching.src.map_library import validate_name

class ImportContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
    def test_provider_routes_and_basement_follow_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=MapImportDialog(Path(tmp),'nightmare','duo')
            self.assertEqual(d.party.currentData(),'duo')
            d.canvas.boxes[-1]=[10,10,80,80]
            d.floor.setCurrentIndex(2)
            d.provider_choice.setCurrentIndex(1)
            self.assertEqual(d.provider,'zhanshi')
            self.assertEqual(d.party.currentData(),'speed')
            d.difficulty.setCurrentIndex(0)
            self.assertEqual([v for _,v in d.floor.items],[1,2])
            self.assertNotIn(-1,d.canvas.boxes)
            self.assertEqual(d.canvas.floor,1)
            d.difficulty.setCurrentIndex(1)
            self.assertEqual(d.canvas.boxes[-1],[10,10,80,80])
            d.close()
    def test_hard_zhanshi_keeps_route_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=MapImportDialog(Path(tmp),'hard','full',provider='zhanshi')
            self.assertFalse(d.party.isHidden())
            self.assertEqual(d.party.currentData(),'full')
            self.assertEqual([v for _,v in d.floor.items],[1,2]);d.close()
    def test_names_are_safe_on_windows_and_keep_chinese(self):
        for value in ['CON','nul.png','COM1','北:凹门','北?凹门','北-凹门.']:
            with self.assertRaises(ValueError):validate_name(value)
        self.assertEqual(validate_name(' 北-凹门（10.30更新） '),'北-凹门（10.30更新）')

if __name__=='__main__':unittest.main()
