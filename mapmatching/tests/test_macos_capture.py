import unittest
import importlib.util
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace
from mapmatching.src.macos_capture import await_callback,select_window


class CaptureTests(unittest.TestCase):
    def test_floating_window_success_missing_and_failure_do_not_crash(self):
        spec=importlib.util.spec_from_file_location('mapmatching.src._macos_test',
            Path(__file__).resolve().parents[1]/'src/macos.py')
        module=importlib.util.module_from_spec(spec)
        appkit=SimpleNamespace(NSWorkspace=Mock(),NSScreen=Mock())
        with patch.dict('sys.modules',{'AppKit':appkit,'Quartz':Mock()}):
            spec.loader.exec_module(module)
            panel=Mock()
            panel.level.return_value=1000
            with patch.object(module,'_panel_for',return_value=panel),patch.object(module,'trace') as trace:
                self.assertTrue(module.keep_floating(123))
                self.assertEqual(trace.call_args.args[0],'mac_panel_configured')
                panel.setLevel_.side_effect=RuntimeError('unavailable')
                self.assertFalse(module.keep_floating(123))
                self.assertEqual(trace.call_args.args[0],'mac_panel_failed')
            with patch.object(module,'_panel_for',return_value=None),patch.object(module,'trace') as trace:
                self.assertFalse(module.keep_floating(123))
                self.assertEqual(trace.call_args.args[0],'overlay_panel_missing')

    def test_native_view_pointer_is_not_treated_as_pid(self):
        spec=importlib.util.spec_from_file_location('mapmatching.src._macos_test',
            Path(__file__).resolve().parents[1]/'src/macos.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'AppKit':Mock(),'Quartz':Mock()}):
            spec.loader.exec_module(module)
        module.window_api.own_window=0x123456789ABC
        with patch.object(module.os,'kill') as kill:
            self.assertTrue(module.window_api.IsWindow(module.window_api.own_window))
            kill.assert_not_called()
        with patch.object(module.os,'kill',side_effect=OverflowError):
            self.assertFalse(module.window_api.IsWindow(0x999999999999))

    def test_callback_success_error_and_timeout(self):
        self.assertEqual(await_callback(lambda cb:cb(42,None)),42)
        with self.assertRaisesRegex(RuntimeError,'denied'):
            await_callback(lambda cb:cb(None,'denied'))
        with self.assertRaises(TimeoutError):
            await_callback(lambda cb:None,timeout=.001)

    def test_target_requires_both_window_and_owner(self):
        def window(wid,pid):
            return SimpleNamespace(windowID=lambda:wid,
                owningApplication=lambda:SimpleNamespace(processID=lambda:pid))
        game=window(8,20)
        self.assertIs(select_window([window(9,20),window(8,30),game],8,20),game)
        with self.assertRaises(RuntimeError):
            select_window([window(9,20),window(8,30)],8,20)
