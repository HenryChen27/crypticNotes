"""Desk-pet behaviour: unprompted actions, doze, drag physics, menu, settings."""
import unittest
from unittest.mock import patch
from PySide6 import QtCore as C, QtWidgets as W
from mapmatching.appearance.skins.doll.animation import pose, body_motion, DURATIONS, LOOPING
from mapmatching.appearance.behavior import PetBehavior, DOZE_AFTER_S, HOVER_COOLDOWN_S


class AnimationTests(unittest.TestCase):
    def test_micro_actions_return_to_rest(self):
        for mood in ('tilt', 'shift', 'stretch', 'wake', 'land'):
            self.assertIn(mood, DURATIONS)
            for endpoint in (0, 1):
                angles, _ = pose(mood, endpoint)
                self.assertTrue(all(abs(a) < 1e-9 for a in angles.values()), mood)
                self.assertTrue(all(abs(v) < 1e-9 for v in body_motion(mood, endpoint).values()), mood)
            self.assertTrue(any(abs(a) > 1 for a in pose(mood, .45)[0].values()), mood)

    def test_doze_loops_with_a_sunk_head(self):
        self.assertIn('doze', LOOPING)
        self.assertGreater(pose('doze', 0)[0]['head'], 5)
        self.assertEqual(body_motion('doze', 0), body_motion('doze', 1))
        self.assertLess(abs(body_motion('doze', .5)['y']), abs(body_motion('idle', .5)['y']))


class BehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def make(self, idle=0.):
        from mapmatching.ui import DraggableGear
        window = W.QWidget()
        window.panel = W.QWidget(window); window.panel.hide()
        gear = DraggableGear(window); gear.pet.enable(True)
        state = {'idle': idle}
        behavior = PetBehavior(gear, window, idle_source=lambda: state['idle'])
        behavior.timer.stop()
        return gear, behavior, state

    def test_dozes_after_long_machine_idle_and_wakes_on_input(self):
        gear, behavior, state = self.make(idle=DOZE_AFTER_S)
        behavior.tick()
        self.assertTrue(behavior.sleeping)
        self.assertEqual(gear.pet.mood, 'doze')
        state['idle'] = 0
        behavior.tick()
        self.assertFalse(behavior.sleeping)
        self.assertEqual(gear.pet.mood, 'wake')

    def test_quiet_mode_never_dozes_or_fidgets(self):
        gear, behavior, state = self.make(idle=DOZE_AFTER_S)
        behavior.quiet = True
        behavior.next_action_at = 0
        behavior.tick()
        self.assertFalse(behavior.sleeping)
        self.assertEqual(gear.pet.mood, 'idle')

    def test_micro_action_fires_when_due_and_not_while_busy(self):
        gear, behavior, state = self.make()
        behavior.next_action_at = 0
        with patch('mapmatching.appearance.behavior.random.choice', return_value='tilt'):
            gear.matching = True
            behavior.tick()
            self.assertEqual(gear.pet.mood, 'idle')
            gear.matching = False
            behavior.tick()
        self.assertEqual(gear.pet.mood, 'tilt')
        self.assertGreater(behavior.next_action_at, 0)

    def test_hover_wave_has_a_cooldown(self):
        gear, behavior, state = self.make()
        self.assertTrue(behavior.hover())
        self.assertFalse(behavior.hover())
        behavior.last_hover -= HOVER_COOLDOWN_S + 1
        self.assertTrue(behavior.hover())

    def test_bubble_turns_the_head_and_fade_restores_on_touch(self):
        gear, behavior, state = self.make()
        behavior.bubble_shown('right')
        self.assertGreater(gear.pet.look, 0)
        behavior.bubble_hidden()
        self.assertEqual(gear.pet.look, 0)
        behavior.last_touch -= 60
        behavior.tick()
        self.assertLess(gear.pet.opacity_target, 1)
        behavior.touched()
        self.assertEqual(gear.pet.opacity_target, 1)

    def test_drag_swing_relaxes_after_release(self):
        gear, behavior, state = self.make()
        pet = gear.pet
        pet.begin_drag()
        for _ in range(6):
            pet.drag_moved(4.); pet._advance_modifiers()
        self.assertTrue(pet.modified)
        self.assertNotEqual(pet.drag_swing, 0)
        pet.end_drag()
        self.assertEqual(pet.mood, 'land')
        for _ in range(80):
            pet._advance_modifiers()
        self.assertEqual((pet.drag_swing, pet.drag_lean, pet.drag_lift), (0., 0., 0.))

    def test_scale_resizes_the_widget_and_keeps_defaults(self):
        gear, behavior, state = self.make()
        self.assertEqual((gear.width(), gear.height()), (112, 132))
        gear.pet.set_scale(1.5)
        self.assertEqual((gear.width(), gear.height()), (168, 198))
        gear.set_game_background(True)
        self.assertEqual((gear.width(), gear.height()), (219, 264))
        gear.set_game_background(False)
        gear.pet.set_scale(1.)
        self.assertEqual((gear.width(), gear.height()), (112, 132))
        self.assertFalse(gear.grab().toImage().isNull())

    def test_right_click_opens_a_menu_instead_of_quitting(self):
        gear, behavior, state = self.make()
        window = gear.window
        window.retry = lambda: None; window.toggle_panel = lambda: None; window.show_module = lambda i: None
        window.state = C.QObject(); window.state.opened = False
        window.open_map = lambda *a, **k: None
        with patch('mapmatching.ui.W.QMenu') as Menu, \
             patch.object(W.QApplication.instance(), 'quit') as quit_:
            gear.context_menu(C.QPoint(0, 0))
            Menu.return_value.exec.assert_called_once()
            labels = [call.args[0] for call in Menu.return_value.addAction.call_args_list]
            self.assertEqual(labels, ['重新识别', '显示叠图', '小游戏', '设置', '退出'])
            quit_.assert_not_called()


if __name__ == '__main__':
    unittest.main()
