import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6 import QtCore as C,QtWidgets as W


class MacInputTests(unittest.TestCase):
    def load(self,name,path):
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_side_button_mapping_and_short_escape_tap(self):
        quartz=Mock()
        with patch.dict(sys.modules,Quartz=quartz,AppKit=Mock()):
            inputs=self.load('test_mac_input',Path('mapmatching/macos_input.py'))
            for vk,button in ((5,3),(6,4)):
                inputs.pressed_virtual_keys(vk)
                self.assertEqual(quartz.CGEventSourceButtonState.call_args.args[1],button)
            mac=self.load('mapmatching.src.test_mac',Path('mapmatching/src/macos.py'))
            keys=mac.Keys();keys.raw_edge(27,False);keys.raw_edge(27,True)
            with patch.dict(sys.modules,{'mapmatching.macos_input':SimpleNamespace(pressed_virtual_keys=lambda key:False)}):
                self.assertEqual(keys.edges(),{27})
                self.assertEqual(keys.edges(),set())

    def test_native_click_through_applies_only_to_passive_windows(self):
        with patch.dict(sys.modules,Quartz=Mock(),AppKit=SimpleNamespace(NSWorkspace=Mock(),NSScreen=Mock())):
            mac=self.load('mapmatching.src.test_mac',Path('mapmatching/src/macos.py'))
            for flags,expected in ((C.Qt.WindowTransparentForInput,1),(C.Qt.Dialog,0)):
                panel=Mock();panel.styleMask.return_value=0;panel.level.return_value=1000;panel.collectionBehavior.return_value=0
                widget=Mock();widget.winId.return_value=7;widget.windowFlags.return_value=flags
                with patch.object(mac,'_panel_for',return_value=panel),patch.object(W.QApplication,'topLevelWidgets',return_value=[widget]):
                    self.assertTrue(mac.keep_floating(7))
                self.assertEqual(panel.setIgnoresMouseEvents_.call_count,expected)
