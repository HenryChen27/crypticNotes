import unittest
from pathlib import Path
from PySide6 import QtWidgets as W
from mapmatching.ui import DraggableGear
from mapmatching.appearance import reaction, SpeechBubble
from mapmatching.appearance.skins.doll.animation import pose


class PetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def test_switch_restores_gear_and_stops_animation(self):
        window = W.QWidget()
        button = DraggableGear(window)
        button.pet.enable(True)
        self.assertTrue(button.pet.enabled)
        button.pet.play('heart')
        self.assertTrue(button.pet.timer.isActive())
        mascot = button.grab().toImage()
        button.pet.enable(False)
        self.assertFalse(button.pet.timer.isActive())
        self.assertEqual(button.width(), 46)
        self.assertNotEqual(mascot, button.grab().toImage())
        button.pet.play('heart')
        self.assertFalse(button.pet.timer.isActive())
        window.close()

    def test_failure_takes_priority_over_floor_text(self):
        self.assertEqual(reaction('匹配失败：楼层信息不足'), 'puzzled')
        self.assertEqual(reaction('地图 · 1层'), 'heart')
        self.assertEqual(reaction('已隐藏'), 'sleep')

    def test_joint_animation_returns_to_rest(self):
        for mood in ('heart', 'happy', 'angry', 'puzzled', 'sleep', 'curious'):
            for endpoint in (0, 1):
                angles, weight = pose(mood, endpoint)
                self.assertEqual(weight, 0)
                self.assertTrue(all(angle == 0 for angle in angles.values()))
        angles, _ = pose('puzzled', .4)
        self.assertLess(angles['right_upper'], -100)
        self.assertNotEqual(angles['right_lower'], angles['right_upper'])

    def test_root_motion_returns_to_rest(self):
        from mapmatching.appearance.skins.doll.animation import body_motion
        for mood in ('happy','angry'):
            for endpoint in (0,1):
                self.assertTrue(all(abs(v)<1e-10 for v in body_motion(mood,endpoint).values()))
            self.assertNotEqual(body_motion(mood,.35)['y'],0)
        self.assertEqual(reaction('快捷键冲突'),'angry')

    def test_speech_tail_tracks_both_sides_and_can_be_disabled(self):
        from PySide6 import QtCore as C
        bubble = SpeechBubble()
        bubble.setText('地图已对齐')
        bubble.adjustSize()
        bubble.move(200, 200)
        bubble.point_at(C.QPoint(180, 220))
        self.assertEqual(bubble.tail, 'left')
        bubble.point_at(C.QPoint(800, 220))
        self.assertEqual(bubble.tail, 'right')
        bubble.point_at(C.QPoint(800, 220), False)
        self.assertIsNone(bubble.tail)
        self.assertEqual(bubble.text(), '地图已对齐')
        bubble.close()
