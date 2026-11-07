"""The 磷焰矿灯 desk pet: poses, light channels, laser, ghost fire, skin switch."""
import json
import math
import unittest
from unittest.mock import patch
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from mapmatching.appearance import create_pet, skin_name, SKINS, PetAnimation, LanternAnimation
from mapmatching.appearance.skins import lantern
from mapmatching.appearance.skins.lantern.animation import pose, body_motion, flight, DURATIONS, LOOPING, CHANNELS, STAGE_MOODS, HOVER, HOVER_DEFAULT
from mapmatching.appearance.skins.lantern.effects import artwork
from mapmatching.appearance.skins.lantern.effects import laser_angle, laser_strength, fire_position, stage_rect


class PoseTests(unittest.TestCase):
    def test_every_mood_returns_to_rest(self):
        for mood in ('heart', 'happy', 'angry', 'puzzled', 'sleep', 'curious', 'tilt', 'shift', 'stretch', 'wake', 'land'):
            self.assertIn(mood, DURATIONS)
            for endpoint in (0, 1):
                angles, _ = pose(mood, endpoint)
                self.assertTrue(all(abs(v) < 1e-9 for v in angles.values()), (mood, angles))
                self.assertTrue(all(abs(v) < 1e-9 for v in body_motion(mood, endpoint).values()), mood)
            self.assertTrue(any(abs(v) > .1 for v in pose(mood, .45)[0].values()), mood)

    def test_channels_are_complete(self):
        for mood in ('idle', 'matching', 'doze', 'angry', 'heart'):
            self.assertEqual(set(pose(mood, .3)[0]), set(CHANNELS), mood)

    def test_idle_breath_is_a_glow_pulse_that_loops(self):
        self.assertEqual(body_motion('idle', 0), body_motion('idle', 1))
        self.assertAlmostEqual(pose('idle', 0)[0]['glow'], pose('idle', 1)[0]['glow'])
        self.assertGreater(pose('idle', .5)[0]['glow'], pose('idle', 0)[0]['glow'])

    def test_matching_scans_and_doze_dims(self):
        self.assertIn('doze', LOOPING)
        self.assertGreater(abs(pose('matching', .25)[0]['scan']), .5)
        self.assertLess(pose('doze', 0)[0]['glow'], -.4)
        self.assertGreater(pose('doze', 0)[0]['tilt'], 0)

    def test_angry_squints_and_curious_blinks_twice(self):
        self.assertGreater(pose('angry', .5)[0]['squint'], .9)
        blinks = [pose('curious', t)[0]['blink'] for t in (0.2, 0.29, 0.38)]
        self.assertGreater(blinks[0], .9)
        self.assertLess(blinks[1], .1)
        self.assertGreater(blinks[2], .9)


class HoverTests(unittest.TestCase):
    def test_flies_up_to_fire_and_comes_back_down(self):
        self.assertEqual(flight(0), 0)
        self.assertGreater(flight(.5), .99)
        self.assertEqual(flight(1), 0)
        self.assertLess(body_motion('angry', .5)['y'], -40)
        self.assertGreater(body_motion('idle', .5)['y'], -14)

    def test_dozing_lands_and_everything_else_hovers(self):
        self.assertEqual(HOVER['doze'], 0)
        self.assertGreater(HOVER_DEFAULT, 10)
        self.assertNotIn('idle', HOVER)

    def test_player_eases_the_hover_height(self):
        W.QApplication.instance() or W.QApplication([])
        button = W.QWidget(); button.window = None
        pet = LanternAnimation(button); pet.enabled = True
        self.assertEqual(pet.hover, HOVER_DEFAULT)
        pet.mood = 'doze'
        heights = []
        for _ in range(40):
            pet._advance_modifiers(); heights.append(pet.hover)
        self.assertEqual(heights[-1], 0)
        self.assertTrue(all(b <= a for a, b in zip(heights, heights[1:])))
        self.assertGreater(heights[0], 10)
        pet.mood = 'idle'
        for _ in range(60):
            pet._advance_modifiers()
        self.assertEqual(pet.hover, HOVER_DEFAULT)

    def test_lantern_has_its_own_cold_symbols(self):
        W.QApplication.instance() or W.QApplication([])
        for kind in ('angry', 'puzzled', 'sleep'):
            image = artwork(kind)
            self.assertIsNotNone(image, kind)
            blue = red = 0
            for x in range(0, image.width(), 5):
                for y in range(0, image.height(), 5):
                    c = image.pixelColor(x, y)
                    if c.alpha() > 100:
                        blue += c.blue() > c.red(); red += c.red() > c.blue()
            self.assertGreater(blue, red*5, kind)


class EffectTests(unittest.TestCase):
    def test_laser_sweeps_the_half_plane_below_and_stays_on_screen(self):
        angles = [laser_angle(t, True, True) for t in (.15, .35, .5, .65, .85)]
        self.assertGreater(angles[0], 150)       # starts pointing down-left
        self.assertLess(angles[2], 30)           # reaches down-right
        self.assertGreater(angles[4], 150)       # and comes back
        for t in (0.2, 0.5, 0.8):
            self.assertTrue(80 <= laser_angle(t, False, False) <= 105)   # cornered: nearly straight down
            self.assertGreaterEqual(laser_angle(t, True, False), 78)     # nothing to the right
        self.assertEqual(laser_strength(0), 0)
        self.assertEqual(laser_strength(.5), 1)
        self.assertEqual(laser_strength(1), 0)

    def test_fire_waits_for_the_climb_then_hangs_beside_the_lens_and_dies(self):
        eye, ground = (500., 300.), (510., 360.)
        start, size, phase = fire_position(0, eye, ground, 1., 'left')
        self.assertEqual((start, size, phase), (eye, 0., 'rising'))   # still inside while the lamp climbs
        spit, size, phase = fire_position(.17, eye, ground, 1., 'left')
        self.assertEqual(phase, 'flight'); self.assertLess(size, .5)
        mid, _, _ = fire_position(.23, eye, ground, 1., 'left')
        self.assertLess(mid[1], eye[1])                               # it arcs up
        hang, size, phase = fire_position(.5, eye, ground, 1., 'left')
        self.assertEqual(phase, 'burning')
        self.assertEqual(size, 1.)
        self.assertLess(hang[1], eye[1])                              # above the lens, never at the ground
        self.assertLess(hang[0], eye[0]-60)
        right, _, _ = fire_position(.5, eye, ground, 1., 'right')
        self.assertGreater(right[0], eye[0]+60)
        self.assertLess(fire_position(.97, eye, ground, 1., 'left')[1], .5)
        self.assertEqual(fire_position(1, eye, ground, 1., 'left')[1], 0)

    def test_lamp_climbs_before_spitting(self):
        from mapmatching.appearance.skins.lantern.animation import body_motion
        self.assertGreater(body_motion('heart', 0.)['y'], -10)
        self.assertLess(body_motion('heart', .2)['y'], -150)
        self.assertLess(body_motion('heart', .6)['y'], -150)
        self.assertGreater(body_motion('heart', 1.)['y'], -10)

    def test_stage_rect_covers_beam_and_fire(self):
        eye, ground = (500., 300.), (510., 360.)
        rect = stage_rect(eye, ground, 1., 'left')
        length = lantern.effects.LASER_LENGTH
        for t in (.2, .5, .8):
            angle = math.radians(laser_angle(t, True, True))
            tip = C.QPoint(int(eye[0]+math.cos(angle)*length), int(eye[1]+math.sin(angle)*length))
            self.assertTrue(rect.contains(tip), (t, tip, rect))
        fire = fire_position(.5, eye, ground, 1., 'right')[0]
        self.assertTrue(rect.contains(C.QPoint(int(fire[0]), int(fire[1])-lantern.effects.FIRE_HEIGHT)))

    def test_stage_paints_something_for_both_tricks(self):
        W.QApplication.instance() or W.QApplication([])
        for mood in STAGE_MOODS:
            image = G.QImage(400, 400, G.QImage.Format_ARGB32_Premultiplied)
            image.fill(C.Qt.transparent)
            p = G.QPainter(image)
            lantern.paint_stage(p, mood, .5, 1.2, (200., 100.), (200., 150.), 1., 'left', True, True)
            p.end()
            pixels = sum(1 for x in range(0, 400, 4) for y in range(0, 400, 4) if image.pixelColor(x, y).alpha() > 0)
            self.assertGreater(pixels, 40, mood)


class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def test_registry_and_settings_fallback(self):
        self.assertEqual([key for key, _ in SKINS], ['doll', 'lantern'])
        self.assertEqual(skin_name({}), 'doll')
        self.assertEqual(skin_name({'pet_skin': 'lantern'}), 'lantern')
        self.assertEqual(skin_name({'pet_skin': 'teapot'}), 'doll')
        self.assertEqual(skin_name(None), 'doll')
        self.assertIsInstance(create_pet(W.QWidget(), 'lantern'), LanternAnimation)
        self.assertIsInstance(create_pet(W.QWidget(), 'doll'), PetAnimation)

    def test_layers_partition_the_image(self):
        pet = LanternAnimation(W.QWidget())
        self.assertEqual(set(pet.layers), set(lantern.PARTS))
        total = G.QImage(*lantern.CANVAS, G.QImage.Format_ARGB32_Premultiplied)
        total.fill(C.Qt.transparent)
        p = G.QPainter(total)
        for layer in pet.layers.values():
            p.drawPixmap(0, 0, layer)
        p.end()
        source = pet.pixmap.toImage().convertToFormat(G.QImage.Format_ARGB32_Premultiplied)
        covered = sum(1 for x in range(0, lantern.CANVAS[0], 3) for y in range(0, lantern.CANVAS[1], 3)
                      if source.pixelColor(x, y).alpha() > 40 and total.pixelColor(x, y).alpha() > 20)
        opaque = sum(1 for x in range(0, lantern.CANVAS[0], 3) for y in range(0, lantern.CANVAS[1], 3)
                     if source.pixelColor(x, y).alpha() > 40)
        self.assertGreater(covered/opaque, .97)

    def test_every_mood_renders_and_records_the_eye(self):
        button = W.QWidget(); button.window = None
        pet = LanternAnimation(button); pet.enabled = True
        for mood in ('idle', 'matching', 'curious', 'heart', 'angry', 'puzzled', 'sleep', 'doze', 'wake', 'tilt', 'shift', 'stretch', 'land'):
            pet.mood = mood
            frame = G.QImage(112, 132, G.QImage.Format_ARGB32_Premultiplied)
            frame.fill(C.Qt.transparent)
            pet._paint_on(frame, .4, .25, (0, 14))
            self.assertTrue(any(frame.pixelColor(x, y).alpha() for x in range(40, 80, 4) for y in range(60, 100, 4)), mood)
            ex, ey = pet.eye_point
            self.assertTrue(28 < ex < 92 and 24 < ey < 110, (mood, pet.eye_point))
            self.assertGreater(pet.ground_point[1], ey)

    def test_gear_switches_skin_keeping_size_and_state(self):
        from mapmatching.ui import DraggableGear
        window = W.QWidget(); window.settings = {'pet_skin': 'lantern'}
        gear = DraggableGear(window)
        self.assertIsInstance(gear.pet, LanternAnimation)
        gear.pet.enable(True); gear.pet.set_scale(1.25)
        self.assertEqual((gear.width(), gear.height()), (140, 182))
        old = gear.pet
        gear.set_skin('doll')
        self.assertIsInstance(gear.pet, PetAnimation)
        self.assertFalse(old.timer.isActive())
        self.assertTrue(gear.pet.enabled and gear.pet.timer.isActive())
        self.assertEqual(gear.pet.scale, 1.25)
        self.assertEqual((gear.width(), gear.height()), (140, 165))   # the doll's own box
        gear.set_skin('lantern')
        self.assertEqual(gear.pet.skin_id, 'lantern')
        gear.set_skin('lantern')      # no-op keeps the same player
        self.assertEqual(gear.pet.skin_id, 'lantern')
        gear.pet.enable(False)
        self.assertEqual(gear.width(), 46)

    def test_stage_only_shows_for_tricks_and_stays_up_with_the_panel(self):
        from mapmatching.ui import DraggableGear
        window = W.QWidget(); window.settings = {'pet_skin': 'lantern'}
        window.panel = W.QWidget(window); window.panel.hide()
        gear = DraggableGear(window); W.QVBoxLayout(window).addWidget(gear); window.show(); gear.pet.enable(True)
        pet = gear.pet
        pet.play('tilt'); pet.advance()
        self.assertIsNone(pet.stage)
        pet.play('angry')
        with patch.object(pet, 'clock') as clock:
            clock.elapsed.return_value = 800
            pet.advance()
            self.assertIsNotNone(pet.stage)
            self.assertTrue(pet.stage.isVisible())
            self.assertGreater(pet.stage.width(), 400)
            self.assertTrue(pet.stage.testAttribute(C.Qt.WA_TransparentForMouseEvents))
            # A click opens the panel and starts the trick together, so the
            # stage keeps showing with the panel open.
            window.panel.show()
            pet.advance()
            self.assertTrue(pet.stage.isVisible())
            window.panel.hide()
            pet.advance()
            self.assertTrue(pet.stage.isVisible())
            clock.elapsed.return_value = DURATIONS['angry']+1
            pet.advance()
        self.assertEqual(pet.mood, 'idle')
        self.assertFalse(pet.stage.isVisible())
        pet.play('heart')
        with patch.object(pet, 'clock') as clock:
            clock.elapsed.return_value = 2000
            pet.advance()
            self.assertTrue(pet.stage.isVisible())
            pet.enable(False)
        self.assertFalse(pet.stage.isVisible())
        window.close()

    def test_matching_loops_without_a_stage(self):
        from mapmatching.ui import DraggableGear
        window = W.QWidget(); window.settings = {'pet_skin': 'lantern'}
        gear = DraggableGear(window); gear.pet.enable(True)
        gear.set_matching(True)
        gear.pet.play('angry')
        self.assertEqual(gear.pet.mood, 'matching')
        with patch.object(gear.pet, 'clock') as clock:
            clock.elapsed.return_value = 5000
            gear.pet.advance()
        self.assertEqual(gear.pet.mood, 'matching')
        self.assertIsNone(gear.pet.stage)
        gear.set_matching(False)
        self.assertEqual(gear.pet.mood, 'idle')
        self.assertFalse(gear.grab().toImage().isNull())


if __name__ == '__main__':
    unittest.main()
