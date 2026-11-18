"""设置面板往哪边展开：桌宠不动，面板去放得下的那一侧。"""
import unittest

from mapmatching.ui import panel_drop, panel_side

# 1920 宽的屏幕，展开后的窗口 380 宽，桌宠连边距占 100。
AREA = (0, 1920)
WIDTH = 380


class PanelSideTests(unittest.TestCase):
    def test_room_on_the_left_keeps_the_old_direction(self):
        # 桌宠在右上角（默认位置）：照旧往左展开。
        self.assertEqual(panel_side(1800, 1900, WIDTH, *AREA), 'left')
        # 刚好放得下也算放得下。
        self.assertEqual(panel_side(280, 380, WIDTH, *AREA), 'left')

    def test_pet_at_the_left_edge_opens_to_the_right(self):
        self.assertEqual(panel_side(0, 100, WIDTH, *AREA), 'right')
        self.assertEqual(panel_side(279, 379, WIDTH, *AREA), 'right')

    def test_second_screen_uses_its_own_edges(self):
        # 副屏在主屏右边，从 1920 开始：贴着它的左边缘也要往右展开。
        self.assertEqual(panel_side(1920, 2020, WIDTH, 1920, 3840), 'right')
        self.assertEqual(panel_side(3700, 3800, WIDTH, 1920, 3840), 'left')

    def test_screen_narrower_than_the_panel_takes_the_smaller_overflow(self):
        # 300 宽的区域放不下 380 的窗口：选伸出去少的一边，剩下的交给 clamp。
        self.assertEqual(panel_side(0, 100, WIDTH, 0, 300), 'right')     # 往右伸出 80，往左伸出 280
        self.assertEqual(panel_side(200, 300, WIDTH, 0, 300), 'left')    # 往左伸出 80，往右伸出 280
        self.assertEqual(panel_side(100, 200, WIDTH, 0, 300), 'left')    # 一样多：保持原来的方向

    def test_collapsed_window_always_fits(self):
        # 收起时窗口只有桌宠那么宽，两边都不伸出，对齐方式回到默认。
        self.assertEqual(panel_side(0, 100, 100, *AREA), 'left')


class PanelDropTests(unittest.TestCase):
    """上下方向：默认往下，下面放不下才往上。屏幕 1019 高，桌宠连边距占 166。"""
    SCREEN = (0, 1019)

    def test_room_below_keeps_the_panel_under_the_pet(self):
        # 桌宠在右上角，窗口想要 615 高。
        self.assertEqual(panel_drop(27, 193, 615, *self.SCREEN), 'down')
        # 刚好放得下也算。
        self.assertEqual(panel_drop(404, 570, 615, *self.SCREEN), 'down')

    def test_pet_near_the_bottom_opens_upward(self):
        self.assertEqual(panel_drop(850, 1016, 615, *self.SCREEN), 'up')
        self.assertEqual(panel_drop(500, 666, 615, *self.SCREEN), 'up')

    def test_content_taller_than_the_screen_goes_where_there_is_more_room(self):
        # 分组全展开时想要 1300 高，哪头都放不下：桌宠在上半屏就往下，在下半屏就往上。
        self.assertEqual(panel_drop(27, 193, 1300, *self.SCREEN), 'down')
        self.assertEqual(panel_drop(850, 1016, 1300, *self.SCREEN), 'up')

    def test_the_decision_uses_the_unsquashed_height(self):
        # 用被屏幕压矮后的高度（比如 266）来判断会永远得到「放得下」。
        self.assertEqual(panel_drop(850, 1016, 266, *self.SCREEN), 'up')
        self.assertEqual(panel_drop(750, 916, 266, *self.SCREEN), 'down')


class RevealTests(unittest.TestCase):
    """面板挪到桌宠上面是布局干的事；淡入动画不能把它拽回动画开始前的位置。"""
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def finish(self, group):
        import time
        deadline = time.monotonic()+2
        done = []
        group.finished.connect(lambda: done.append(True))
        while not done and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(done, '动画没有结束')

    def test_fade_without_distance_leaves_the_position_to_the_layout(self):
        from PySide6 import QtCore as C, QtWidgets as W
        from mapmatching.theme import reveal
        parent = W.QWidget(); child = W.QWidget(parent); child.hide()
        child.move(3, 171)                       # 上一次布局留下的位置：在桌宠下面
        group = reveal(child, distance=0, duration=20)
        child.move(3, 3)                         # 布局随后把它排到桌宠上面
        self.finish(group)
        self.assertEqual(child.pos(), C.QPoint(3, 3), '淡入结束时把面板拽回了旧位置，会盖住桌宠')
        self.assertIsNone(child.graphicsEffect())
        parent.deleteLater()

    def test_slide_still_settles_where_it_started(self):
        from PySide6 import QtCore as C, QtWidgets as W
        from mapmatching.theme import reveal
        parent = W.QWidget(); child = W.QWidget(parent); child.hide()
        child.move(10, 40)
        self.finish(reveal(child, distance=6, duration=20))
        self.assertEqual(child.pos(), C.QPoint(10, 40))
        parent.deleteLater()


if __name__ == '__main__':
    unittest.main()
