"""快捷键可选项：键表、Qt 映射，以及鼠标键真的能走完「按下-松开-再按下」。

不合成任何输入：Raw Input 那条用例是自己造一条 WM_INPUT 缓冲喂给 `_read()`，
键盘那些则是直接问映射函数。
"""
import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from mapmatching.mouse_input import MouseWatcher, RAWINPUT, RIM_TYPEMOUSE
from mapmatching.src.windows import Keys
from mapmatching.ui import (C, HOTKEY_LABELS, HOTKEYS, hotkey_from_event, hotkey_text,
                            resolve_hotkeys)


def event(key, modifiers=C.Qt.NoModifier):
    return SimpleNamespace(key=lambda: key, modifiers=lambda: modifiers)


class HotkeyTableTests(unittest.TestCase):
    def test_mouse_buttons_and_capslock_are_offered(self):
        self.assertEqual(HOTKEYS['MOUSE_RIGHT'], 0x02)
        self.assertEqual(HOTKEYS['MOUSE_MIDDLE'], 0x04)
        self.assertEqual(HOTKEYS['MOUSE_SIDE1'], 0x05)
        self.assertEqual(HOTKEYS['MOUSE_SIDE2'], 0x06)
        self.assertEqual(HOTKEYS['CAPSLOCK'], 0x14)
        self.assertEqual(HOTKEYS['NUMLOCK'], 0x90)
        self.assertEqual(HOTKEYS['CTRL'], 0x11)
        self.assertEqual(HOTKEYS['SHIFT'], 0x10)
        self.assertEqual(HOTKEYS['ALT'], 0x12)

    def test_win_key_stays_out(self):
        """单独按 Win 会弹开始菜单，正违背「挑一个不冲突的键」。"""
        for vk in (0x5B, 0x5C):
            self.assertNotIn(vk, HOTKEYS.values())

    def test_only_the_left_button_stays_out(self):
        """左键是游戏里拖动地图的手势，助手靠它判断「停手了，重新贴合」，不能绑。

        右键能绑：跟随只看左键和滚轮（`map_interacting()`），右键进来不影响它 ——
        这条由 `tests/test_frame_guard.py` 的 `test_only_left_button_or_wheel_...` 守着。
        """
        self.assertNotIn(0x01, HOTKEYS.values())
        self.assertIn(0x02, HOTKEYS.values())

    def test_virtual_key_codes_are_what_they_claim(self):
        for name, vk in (('UP', 0x26), ('DOWN', 0x28), ('LEFT', 0x25), ('RIGHT', 0x27),
                         ('NUM0', 0x60), ('NUM9', 0x69), ('NUMMUL', 0x6A),
                         ('LBRACKET', 0xDB), ('GRAVE', 0xC0)):
            self.assertEqual(HOTKEYS[name], vk, name)

    def test_internal_names_never_reach_the_user(self):
        """面板和提示里显示的是 hotkey_text()，不是键表里的英文名。"""
        for name in HOTKEYS:
            if len(name) == 1 or (name[0] == 'F' and name[1:].isdigit()):
                continue          # 单字符和 F1~F12 本身就是给人看的
            self.assertNotEqual(hotkey_text(name), name, f'{name} 没有中文名')

    def test_labels_and_table_agree(self):
        for name in HOTKEY_LABELS:
            self.assertIn(name, HOTKEYS, f'{name} 有名字却不在键表里')


class QtMappingTests(unittest.TestCase):
    def test_letters_digits_and_function_keys(self):
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_G)), 'G')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_5)), '5')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_F1)), 'F1')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_F12)), 'F12')

    def test_numpad_is_not_mistaken_for_a_modifier(self):
        pad = C.Qt.KeypadModifier
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_7, pad)), 'NUM7')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Asterisk, pad)), 'NUMMUL')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Plus, pad)), 'NUMADD')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Period, pad)), 'NUMDEC')
        # 同一个物理键在不在小键盘上是两个身份 —— 用户要能分开绑
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Minus)), 'MINUS')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Minus, pad)), 'NUMSUB')

    def test_modifier_keys_are_their_own_shortcut(self):
        """按 Ctrl 时 modifiers 里必然带着 CtrlModifier，不能因此被当成组合键拒掉。"""
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Control, C.Qt.ControlModifier)), 'CTRL')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Shift, C.Qt.ShiftModifier)), 'SHIFT')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Alt, C.Qt.AltModifier)), 'ALT')
        # 但 Ctrl+G 这种组合仍然拒绝：一个键就是一个身份。
        self.assertIsNone(hotkey_from_event(event(C.Qt.Key_G, C.Qt.ControlModifier)))

    def test_function_keys_past_twelve(self):
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_F13)), 'F13')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_F24)), 'F24')
        self.assertEqual(HOTKEYS['F13'], 0x7C)
        self.assertEqual(HOTKEYS['F24'], 0x87)

    def test_capslock_arrows_and_punctuation(self):
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_CapsLock)), 'CAPSLOCK')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_NumLock)), 'NUMLOCK')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Up)), 'UP')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_BracketLeft)), 'LBRACKET')
        self.assertEqual(hotkey_from_event(event(C.Qt.Key_Backslash)), 'BACKSLASH')

    def test_real_modifiers_are_refused(self):
        self.assertIsNone(hotkey_from_event(event(C.Qt.Key_G, C.Qt.ControlModifier)))
        self.assertIsNone(hotkey_from_event(event(C.Qt.Key_G, C.Qt.AltModifier)))
        self.assertIsNone(hotkey_from_event(event(C.Qt.Key_G, C.Qt.ShiftModifier | C.Qt.KeypadModifier)))

    def test_escape_stays_reserved(self):
        self.assertIsNone(hotkey_from_event(event(C.Qt.Key_Escape)))

    def test_everything_the_mapping_returns_is_bindable(self):
        """映射出来的名字必须都在键表里，否则设置里选得中、运行时查不到。"""
        for key in (C.Qt.Key_A, C.Qt.Key_Z, C.Qt.Key_0, C.Qt.Key_9, C.Qt.Key_F1,
                    C.Qt.Key_F12, C.Qt.Key_CapsLock, C.Qt.Key_Up, C.Qt.Key_NumLock,
                    C.Qt.Key_QuoteLeft, C.Qt.Key_Apostrophe, C.Qt.Key_Backslash,
                    C.Qt.Key_Semicolon, C.Qt.Key_Equal, C.Qt.Key_Comma):
            self.assertIn(hotkey_from_event(event(key)), HOTKEYS)
        for key in (C.Qt.Key_0, C.Qt.Key_Asterisk, C.Qt.Key_Plus, C.Qt.Key_Minus,
                    C.Qt.Key_Period, C.Qt.Key_Slash):
            self.assertIn(hotkey_from_event(event(key, C.Qt.KeypadModifier)), HOTKEYS)


class MouseHotkeyTests(unittest.TestCase):
    """鼠标键没有键盘事件，只能走 Raw Input；这里盯的是它**反复**可用。"""

    def test_side_button_survives_without_mouse_raw_input(self):
        """鼠标监听没注册上时，侧键只能靠轮询，也必须能反复触发。

        旧实现只有一个 `raw_active`：键盘注册成功就整体走「只置位、不清位」那一支，
        于是侧键的按下态永远清不掉 —— 按一次有反应，之后按多少次都没反应。
        键盘 Raw Input 不负责鼠标键，所以它不能替鼠标键做这个决定。
        """
        keys = Keys()
        keys.raw_keyboard = True
        keys.raw_mouse = False
        keys.toggle_key = HOTKEYS['MOUSE_SIDE1']
        held = {0x05}
        with patch('mapmatching.src.windows.user32.GetAsyncKeyState',
                   side_effect=lambda key: 0x8000 if key in held else 0):
            self.assertEqual(keys.edges(), {0x05})
            held.clear()
            self.assertEqual(keys.edges(), set())
            held.add(0x05)
            self.assertEqual(keys.edges(), {0x05})
            held.clear()
            self.assertEqual(keys.edges(), set())

    def test_raw_mouse_still_works_when_polling_is_blind(self):
        """提权游戏下 UIPI 让 GetAsyncKeyState 恒返回 0，此时唯一的信号是 Raw Input。"""
        keys = Keys()
        keys.raw_keyboard = keys.raw_mouse = True
        keys.toggle_key = HOTKEYS['MOUSE_SIDE2']
        with patch('mapmatching.src.windows.user32.GetAsyncKeyState', return_value=0):
            keys.raw_edge(0x06, False)
            self.assertEqual(keys.edges(), {0x06})
            keys.raw_edge(0x06, True)
            keys.raw_edge(0x06, False)
            self.assertEqual(keys.edges(), {0x06})

    @staticmethod
    def feed_button(ulButtons):
        """造一条真的 WM_INPUT 缓冲喂给 `_read()`，走完解析那一层。"""
        keys = Keys()
        watcher = MouseWatcher(keys)
        raw = RAWINPUT()
        raw.header.dwType = RIM_TYPEMOUSE
        raw.data.mouse.ulButtons = ulButtons
        payload = bytes(raw)

        def get_raw_input_data(handle, kind, buffer, size, header_size):
            if not buffer:
                size._obj.value = len(payload)
                return 0
            ctypes.memmove(buffer, payload, len(payload))
            size._obj.value = len(payload)
            return len(payload)

        edges = []
        keys.raw_edge = lambda key, released: edges.append((key, released))
        with patch('mapmatching.mouse_input.user32.GetRawInputData',
                   side_effect=get_raw_input_data):
            watcher._read(0)
        return edges

    def test_mouse_watcher_turns_a_side_button_event_into_an_edge(self):
        self.assertEqual(self.feed_button(0x0040), [(0x05, False)])   # BUTTON_4_DOWN

    def test_mouse_watcher_turns_a_right_button_event_into_an_edge(self):
        """右键走的是同一条线：Raw Input -> MouseWatcher._read -> Keys.raw_edge。

        左键同样会被转发，但 `Keys.raw_edge` 只认自己关心的键，而左键永远不在
        `HOTKEYS` 里，所以它到不了快捷键状态机。
        """
        self.assertEqual(self.feed_button(0x0004), [(0x02, False)])   # BUTTON_2_DOWN
        self.assertEqual(self.feed_button(0x0008), [(0x02, True)])    # BUTTON_2_UP

    def test_mouse_watcher_without_keys_is_still_fine(self):
        """跟随功能用的那个 watcher 不传 keys，行为一个字都不该变。"""
        watcher = MouseWatcher()
        watcher._hotkey_edge(0x05, False)      # 不该炸
        self.assertIsNone(watcher.keys)

class ResolveHotkeysTests(unittest.TestCase):
    def test_conflicting_saved_pair_gets_split(self):
        """旧配置里开关键和隐藏键撞在一起时，开关键必须活下来。

        `tick()` 先看隐藏键再看开关键，撞上就等于开关键永远轮不到。
        """
        hotkey, hide = resolve_hotkeys({'hotkey': 'BACKSPACE', 'hide_hotkey': 'BACKSPACE'})
        self.assertEqual(hotkey, 'BACKSPACE')
        self.assertNotEqual(hide, hotkey)

    def test_unknown_names_fall_back_to_defaults(self):
        self.assertEqual(resolve_hotkeys({'hotkey': 'NOPE', 'hide_hotkey': 'NOPE2'}),
                         ('G', 'BACKSPACE'))
        self.assertEqual(resolve_hotkeys({}), ('G', 'BACKSPACE'))

    def test_mouse_keys_are_kept(self):
        self.assertEqual(resolve_hotkeys({'hotkey': 'MOUSE_SIDE1', 'hide_hotkey': 'MOUSE_SIDE2'}),
                         ('MOUSE_SIDE1', 'MOUSE_SIDE2'))


if __name__ == '__main__':
    unittest.main()
