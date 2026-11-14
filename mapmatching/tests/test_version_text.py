import datetime
import unittest

from mapmatching.module_ui import windows_version_text


class WindowsVersionTextTests(unittest.TestCase):
    def test_build_stamp_is_shown_as_build_time(self):
        build = 1794573445970908900
        expected = datetime.datetime.fromtimestamp(build / 1e9).strftime('%Y.%m.%d %H:%M')
        self.assertEqual(windows_version_text({'build': build}), expected)
        self.assertLessEqual(len(expected), 16)

    def test_explicit_version_wins_and_bad_stamps_do_not_raise(self):
        self.assertEqual(windows_version_text({'version': '1.2', 'build': 5}), '1.2')
        self.assertEqual(windows_version_text({}), '未知')
        self.assertEqual(windows_version_text({'build': 'abc'}), '未知')


if __name__ == '__main__':
    unittest.main()
