import unittest
import ctypes
from unittest.mock import patch
from mapmatching.keyboard_input import KeyboardWatcher, user32, RIDEV_INPUTSINK
from mapmatching.src.windows import Keys


class RegistrationTests(unittest.TestCase):
    def test_read_failure_is_distinct_from_no_message(self):
        watcher=KeyboardWatcher(Keys())
        with patch.object(user32,'GetRawInputData',return_value=0xFFFFFFFF):
            watcher._read(123)
        self.assertEqual(watcher.messages,1)
        self.assertEqual(watcher.received,0)
        self.assertEqual(watcher.read_errors,1)
        self.assertEqual(watcher.last_read_error['stage'],'size')

    def test_keyboard_packet_reaches_shortcut_state(self):
        from mapmatching.keyboard_input import RAWINPUTHEADER, RAWKEYBOARD
        keys=Keys();watcher=KeyboardWatcher(keys)
        header=RAWINPUTHEADER();header.dwType=1
        key=RAWKEYBOARD();key.VKey=keys.toggle_key
        packet=bytes(header)+bytes(key)
        def read(handle,command,buffer,size,header_size):
            size._obj.value=len(packet)
            if buffer is None:return 0
            ctypes.memmove(buffer,packet,len(packet))
            return len(packet)
        with patch.object(user32,'GetRawInputData',side_effect=read):
            watcher._read(123)
        self.assertEqual(watcher.received,1)
        self.assertEqual(watcher.shortcut_events,1)
        self.assertEqual(keys.pending_edges,{keys.toggle_key})

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
