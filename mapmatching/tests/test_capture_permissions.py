import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
from mapmatching import window_map_capture as capture

class CapturePermissionTests(unittest.TestCase):
 def tearDown(self):capture.allow_capture_retry()
 def test_rejection_blocks_native_start_until_manual_retry(self):
  capture.allow_capture_retry()
  with patch('windows_capture.WindowsCapture',side_effect=RuntimeError('HRESULT 0x80070005 E_ACCESSDENIED')) as factory:
   for _ in range(3):
    with self.assertRaises(PermissionError):capture.WindowSnapshot(123)
   self.assertEqual(factory.call_count,1)
   capture.allow_capture_retry()
   with self.assertRaises(PermissionError):capture.WindowSnapshot(123)
   self.assertEqual(factory.call_count,2)
 def test_ui_does_not_fallback_after_permission_denied(self):
  from mapmatching.ui import Companion
  subject=SimpleNamespace(state=SimpleNamespace(accepts=lambda token:True),foreground_lost=lambda:False,
   capture_rect=lambda:(0,0,640,400),demo_window=None,target=1,close_map=Mock(),notify=Mock(),restore_capture_companion=Mock())
  with patch('mapmatching.game_scene_watch.find_game_window',return_value=123),patch('mapmatching.window_map_capture.WindowSnapshot',side_effect=PermissionError('denied')),patch('mapmatching.ui.native.capture') as fallback:
   Companion.capture_after_hide(subject,1)
  fallback.assert_not_called();subject.close_map.assert_called_once_with(silent=True)
  self.assertLess(len(subject.notify.call_args.args[0]),100)
 def test_error_classification(self):
  self.assertTrue(capture.capture_denied('The user declined access'))
  self.assertFalse(capture.capture_denied('window capture timeout'))

if __name__=='__main__':unittest.main()
