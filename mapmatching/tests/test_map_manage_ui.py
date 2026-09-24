"""点「移除」必须真的写进 `disabled.json`。

这条曾经是坏的，而且坏得**没有任何自动化的东西看得见**：确认框 `accept()` 之后紧跟着
一个由它自己触发的 `WindowDeactivate`，`PanelDialog.event()` 当场 `self.reject()`，
`done(Rejected)` 把刚写进去的 `Accepted` 覆盖掉，`exec()` 于是返回 Rejected，
`mutate()` 静默 return —— 不写盘、不报错、两个框都还开着。用户看到的是
「点了移除但没反应」。

所以这里必须走**真模态** `exec()`：`map_manage_smoke` 用的是 `show()`（非模态），
那一刻 `activeModalWidget()` 永远不是对话框自己，这条路径压根不会被触发 ——
这正是它一直是绿的原因。驱动方式是在 `exec()` 的嵌套事件循环里用
`QTimer.singleShot` 分步点按钮。
"""
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from mapmatching.ui import W, C
from mapmatching.theme import ChalkButton
from mapmatching.map_manage_ui import ConfirmDialog, MapManageDialog, RowButton
from mapmatching.src import mapstore
from mapmatching.src.map_library import add_map
from PySide6.QtTest import QTest


def app():
    return W.QApplication.instance() or W.QApplication([])


def register(root, name, difficulty, mode, marker):
    """和 map_manage_smoke 同一套夹具几何；marker 只扰动哈希，避免撞 pixel_sha256。"""
    image = np.zeros((300, 300, 3), np.uint8)
    image[40:220, 40:100] = 120
    image[150:220, 40:240] = 120
    image[5:15, 5:15] = marker
    source = root/f'{name}.png'
    cv2.imencode('.png', image)[1].tofile(source)
    regions = ([dict(floor=1, bbox=[0, 0, 300, 150]), dict(floor=2, bbox=[0, 150, 300, 300])]
               if difficulty == 'hard'
               else [dict(floor=-1, bbox=[0, 0, 300, 240]), dict(floor=1, bbox=[0, 150, 300, 300])])
    return add_map(root, source, name, difficulty, mode, regions)


def drive_removal(root, map_id, name):
    """开管理框、点那一行的「移除」、在确认框上点确认，全程走真模态。

    返回看到的对话框类型序列，好让调用方断言「确认框确实弹出来过」——
    否则一个什么都没弹的测试也能「通过」。
    """
    instance = app()
    dialog = MapManageDialog(root, map_id.split('/')[0], None)
    seen = []

    def click_remove():
        row = dialog._row_of[map_id]
        # QTest.mouseClick 默认点控件中心；被滚出可视区时那一点会落在对话框
        # geometry 之外，触发「点到框外」的 reject —— 那就不是在测这条路径了。
        dialog.scroll.ensureWidgetVisible(row, 0, 40)
        for _ in range(3):
            instance.processEvents()
        QTest.mouseClick(row.findChild(RowButton), C.Qt.LeftButton)

    def confirm():
        box = instance.activeModalWidget()
        seen.append(type(box).__name__ if box is not None else None)
        if isinstance(box, ConfirmDialog):
            box.findChildren(ChalkButton)[-1].click()
        C.QTimer.singleShot(200, dialog.reject)   # 收掉管理框，结束 exec

    C.QTimer.singleShot(200, click_remove)
    C.QTimer.singleShot(600, confirm)
    C.QTimer.singleShot(8000, instance.quit)      # 兜底：卡住也不要挂死测试进程
    dialog.exec()
    return seen


class RemovalThroughTheModalConfirm(unittest.TestCase):

    def test_confirm_actually_writes_the_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '甲', 'hard', None, 30)
            seen = drive_removal(root, 'hard/甲', '甲')
            self.assertEqual(seen, ['ConfirmDialog'], '确认框没弹出来，这个测试就没测到东西')
            self.assertEqual(mapstore.read_disabled(root/'maps'), [])
            self.assertEqual(mapstore.read_manifest(root/'maps'), [])
            self.assertFalse((root/'maps/hard/甲.png').exists())
            self.assertTrue((root/'甲.png').exists())

    def test_cancelling_the_confirm_changes_nothing(self):
        """反向：点「取消」不该动盘 —— 免得把「一律写盘」当成通过。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '乙', 'hard', None, 60)
            instance = app()
            dialog = MapManageDialog(root, 'hard', None)
            seen = []

            def click_remove():
                row = dialog._row_of['hard/乙']
                dialog.scroll.ensureWidgetVisible(row, 0, 40)
                for _ in range(3):
                    instance.processEvents()
                QTest.mouseClick(row.findChild(RowButton), C.Qt.LeftButton)

            def cancel():
                box = instance.activeModalWidget()
                seen.append(type(box).__name__ if box is not None else None)
                if isinstance(box, ConfirmDialog):
                    box.findChildren(ChalkButton)[0].click()   # 第一个是取消
                C.QTimer.singleShot(200, dialog.reject)

            C.QTimer.singleShot(200, click_remove)
            C.QTimer.singleShot(600, cancel)
            C.QTimer.singleShot(8000, instance.quit)
            dialog.exec()
            self.assertEqual(seen, ['ConfirmDialog'])
            self.assertEqual(mapstore.read_disabled(mapstore.maps_dir(root)), [])


if __name__ == '__main__':
    unittest.main()
