import ctypes
import runpy
import sys
import unittest
from unittest.mock import Mock,patch


class AdminLauncherTests(unittest.TestCase):
    def test_packaged_double_click_requests_elevation(self):
        shell=Mock(return_value=42)
        with patch.object(sys,'argv',['assistant.exe']), \
             patch.object(sys,'frozen',True,create=True), \
             patch('multiprocessing.freeze_support'), \
             patch.object(ctypes.windll.shell32,'IsUserAnAdmin',return_value=0), \
             patch.object(ctypes.windll.shell32,'ShellExecuteW',shell):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_module('mapmatching.launch',run_name='__main__')
        self.assertEqual(stop.exception.code,0)
        self.assertEqual(shell.call_args.args[1],'runas')

    def test_packaged_self_test_does_not_request_elevation(self):
        with patch.object(sys,'argv',['assistant.exe','--self-test','result.json']), \
             patch.object(sys,'frozen',True,create=True), \
             patch('multiprocessing.freeze_support'), \
             patch('mapmatching.portable_check.run') as check, \
             patch.object(ctypes.windll.shell32,'ShellExecuteW') as shell:
            with self.assertRaises(SystemExit):
                runpy.run_module('mapmatching.launch',run_name='__main__')
        shell.assert_not_called()
        check.assert_called_once_with('result.json')

    def test_requests_standard_uac_without_starting_ui_in_parent(self):
        shell=Mock(return_value=42)
        with patch.object(sys,'argv',['launch','--admin','--local-test']), \
             patch.object(ctypes.windll.shell32,'IsUserAnAdmin',return_value=0), \
             patch.object(ctypes.windll.shell32,'ShellExecuteW',shell):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_module('mapmatching.launch',run_name='__main__')
        self.assertEqual(stop.exception.code,0)
        args=shell.call_args.args
        self.assertEqual(args[1],'runas')
        self.assertIn('--local-test',args[3])
        self.assertNotIn('--admin',args[3])

    def test_cancel_does_not_claim_success(self):
        with patch.object(sys,'argv',['launch','--admin']), \
             patch.object(ctypes.windll.shell32,'IsUserAnAdmin',return_value=0), \
             patch.object(ctypes.windll.shell32,'ShellExecuteW',Mock(return_value=5)), \
             patch.object(ctypes.windll.user32,'MessageBoxW') as message:
            with self.assertRaises(SystemExit) as stop:
                runpy.run_module('mapmatching.launch',run_name='__main__')
        self.assertEqual(stop.exception.code,1)
        message.assert_called_once()
