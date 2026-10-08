import unittest
from unittest.mock import patch
from mapmatching.keyboard_input import KeyboardWatcher, user32, RIDEV_INPUTSINK
from mapmatching.src.windows import Keys


class RegistrationTests(unittest.TestCase):
    def check(self, owner, flags, expected):
        watcher=KeyboardWatcher(Keys())
        def query(devices,count,size):
            if devices is None:
                count._obj.value=1
                return 0
            devices[0].usUsagePage=1;devices[0].usUsage=6
            devices[0].hwndTarget=owner;devices[0].dwFlags=flags
            return 1
        with patch.object(user32,'GetRegisteredRawInputDevices',side_effect=query), \
             patch.object(watcher,'register',return_value=True) as register, \
             patch('mapmatching.src.ui_trace.trace'):
            watcher.maintain(123)
            self.assertEqual(register.call_count,expected)
            watcher.maintain(123)
            self.assertEqual(register.call_count,expected)

    def test_replaced_window_is_repaired(self):self.check(456,RIDEV_INPUTSINK,1)
    def test_foreground_only_registration_is_repaired(self):self.check(123,0,1)
    def test_healthy_registration_is_not_changed(self):self.check(123,RIDEV_INPUTSINK,0)

if __name__=='__main__':unittest.main()
