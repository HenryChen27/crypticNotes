import ctypes
import runpy
import sys
import unittest
from unittest.mock import Mock,patch


class AdminLauncherTests(unittest.TestCase):
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
