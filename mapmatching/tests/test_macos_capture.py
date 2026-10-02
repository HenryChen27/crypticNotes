import unittest
from types import SimpleNamespace
from mapmatching.src.macos_capture import await_callback,select_window


class CaptureTests(unittest.TestCase):
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
