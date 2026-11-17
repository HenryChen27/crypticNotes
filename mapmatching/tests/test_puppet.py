"""The 守财木偶 desk pet: its rig, its poses, and the game where it steals the pointer."""
import random
import unittest
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from mapmatching.appearance import create_pet, skin_name, SKINS
from mapmatching.appearance.puppet import PuppetAnimation
from mapmatching.appearance.skins import puppet
from mapmatching.appearance.skins.puppet.animation import pose, body_motion, DURATIONS, LOOPING, HOLD, HEIST_MOODS, CHANNELS
from mapmatching.appearance import heist as heist_module
from mapmatching.appearance.heist import Heist, STILL_S, pick_loot, new_pity, load_relics, COMMON, RARE, RARE_CHANCE, PITY, TIERS

REGULAR = ('heart', 'happy', 'angry', 'puzzled', 'sleep', 'curious', 'tilt', 'shift', 'stretch', 'wake', 'land')


class PoseTests(unittest.TestCase):
    def test_regular_moods_return_to_rest(self):
        for mood in REGULAR+('rejoice',):
            self.assertIn(mood, DURATIONS)
            for endpoint in (0, 1):
                self.assertTrue(all(abs(v) < 1e-9 for v in pose(mood, endpoint)[0].values()), mood)
                self.assertTrue(all(abs(v) < 1e-9 for v in body_motion(mood, endpoint).values()), mood)
            self.assertTrue(any(abs(v) > .1 for v in pose(mood, .45)[0].values()), mood)

    def test_every_mood_has_every_channel_and_a_duration(self):
        for mood in ('idle', 'matching', 'doze')+REGULAR+HEIST_MOODS:
            self.assertEqual(set(pose(mood, .3)[0]), set(CHANNELS), mood)
            self.assertEqual(set(body_motion(mood, .3)), {'x', 'y', 'torso', 'squash'}, mood)
            if mood != 'idle' and mood != 'matching':
                self.assertIn(mood, DURATIONS)

    def test_loops_close_and_knees_only_bend_back(self):
        for mood in LOOPING:
            for name, value in pose(mood, 0)[0].items():
                self.assertAlmostEqual(value, pose(mood, 1)[0][name], places=6, msg=(mood, name))
        for mood in HEIST_MOODS:
            for i in range(21):
                angles = pose(mood, i/20)[0]
                self.assertLessEqual(angles['knee_l'], 1e-9, mood)
                self.assertLessEqual(angles['knee_r'], 1e-9, mood)

    def test_the_fall_ends_where_lying_begins_and_getting_up_ends_standing(self):
        self.assertEqual(set(HOLD), {'grab', 'trip', 'getup'})
        self.assertAlmostEqual(pose('trip', 1)[0]['lean'], puppet.LIE_LEAN)
        self.assertAlmostEqual(pose('down', 0)[0]['lean'], puppet.LIE_LEAN)
        self.assertAlmostEqual(body_motion('trip', 1)['x'], puppet.LIE_SHIFT)
        self.assertAlmostEqual(pose('getup', 1)[0]['lean'], 0.)
        self.assertAlmostEqual(body_motion('getup', 1)['x'], 0.)


class PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def make(self):
        button = W.QWidget(); button.window = None
        pet = PuppetAnimation(button); pet.enabled = True
        button.setFixedSize(*pet.widget_size())
        return button, pet

    def render(self, pet, mood, t=.4):
        w, h = pet.widget_size()
        pet.mood = mood; pet._from = None
        frame = G.QImage(w, h, G.QImage.Format_ARGB32_Premultiplied)
        frame.fill(C.Qt.transparent)
        pet._paint_on(frame, t, pet.render_scale, pet.origin_for(w, h))
        return frame

    def columns(self, frame):
        return [x for x in range(frame.width()) if any(frame.pixelColor(x, y).alpha() > 60 for y in range(0, frame.height(), 3))]

    def test_registered_with_all_its_layers(self):
        self.assertEqual([key for key, _ in SKINS], ['doll', 'lantern', 'puppet'])
        self.assertEqual(skin_name({'pet_skin': 'puppet'}), 'puppet')
        pet = create_pet(W.QWidget(), 'puppet')
        self.assertIsInstance(pet, PuppetAnimation)
        self.assertEqual(set(pet.layers), set(puppet.LAYERS))
        self.assertFalse(pet.waiting_pixmap().isNull())

    def test_every_mood_fits_inside_the_widget(self):
        button, pet = self.make()
        for sack in (True, False):
            pet.has_sack = sack
            for mood in ('idle', 'matching', 'doze')+REGULAR+HEIST_MOODS:
                for t in (.1, .4, .7, .95):
                    frame = self.render(pet, mood, t)
                    columns = self.columns(frame)
                    self.assertTrue(columns, mood)
                    edge = [y for y in range(frame.height()) if frame.pixelColor(0, y).alpha() > 60
                            or frame.pixelColor(frame.width()-1, y).alpha() > 60]
                    self.assertFalse(edge, (mood, t, sack))

    def test_facing_mirrors_and_the_sack_comes_off(self):
        button, pet = self.make()
        left = self.columns(self.render(pet, 'idle'))
        pet.facing = -1
        right = self.columns(self.render(pet, 'idle'))
        width = pet.widget_size()[0]
        self.assertAlmostEqual(left[0], width-1-right[-1], delta=2)
        pet.facing = 1
        pet.has_sack = False
        bare = self.columns(self.render(pet, 'idle'))
        self.assertLess(bare[-1], left[-1]-20)
        self.assertAlmostEqual(pet.widget_point(puppet.REACH).x(), width-pet_point_mirrored(pet), delta=.01)

    def test_act_overrides_matching_and_hold_keeps_the_last_frame(self):
        button, pet = self.make()
        button.matching = True
        pet.timer.start()
        pet.play('heart')
        self.assertNotEqual(pet.mood, 'heart')
        pet.act('trip')
        self.assertEqual(pet.mood, 'trip')
        pet.clock = _Elapsed(10**6)
        pet.advance()
        self.assertEqual(pet.mood, 'trip')        # a HOLD mood does not fall back to idle
        pet.act('rejoice'); pet.clock = _Elapsed(10**6); button.matching = False
        pet.advance()
        self.assertEqual(pet.mood, 'idle')
        pet.timer.stop()


def pet_point_mirrored(pet):
    pet.facing = -1
    x = pet.widget_point(puppet.REACH).x()
    pet.facing = 1
    return x


class _Elapsed:
    def __init__(self, value): self.value = value
    def elapsed(self): return self.value
    def isValid(self): return True
    def restart(self): self.value = 0
    def start(self): self.value = 0


class FakeInputs:
    def __init__(self): self.left = False; self.escape = False
    def left_down(self): return self.left
    def escape_down(self): return self.escape


class HeistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        from mapmatching.ui import DraggableGear
        self.window = W.QWidget(None, C.Qt.Tool | C.Qt.FramelessWindowHint)
        self.window.settings = {'pet_skin': 'puppet'}
        self.gear = DraggableGear(self.window)
        layout = W.QVBoxLayout(self.window); layout.setContentsMargins(3, 3, 3, 3); layout.addWidget(self.gear)
        self.gear.pet.enable(True)
        self.window.adjustSize()
        area = W.QApplication.primaryScreen().availableGeometry()
        self.area = area
        self.window.move(area.center().x(), area.center().y()-80)
        self.window.show()
        self.now = 1000.
        self.pointer = C.QPoint(area.center().x()-300, area.center().y())
        self.inputs = FakeInputs()
        self.heist = Heist(self.gear, self.window, inputs=self.inputs, clock=lambda: self.now,
                           cursor=lambda: C.QPoint(self.pointer), rng=random.Random(4))
        self.heist.watch.stop()
        self.window.heist = self.heist
        self.home = C.QPoint(self.window.pos())

    def tearDown(self):
        self.heist.abort()
        for extra in (self.heist.sprite, self.heist.sack):
            if extra is not None:
                extra.close()
        self.gear.pet.release()
        self.gear.exit_zone.close()
        self.window.close()

    def run_for(self, seconds, until=None, step=.016):
        end = self.now+seconds
        while self.now < end:
            self.now += step
            self.heist.tick()
            if until is not None and until():
                return True
        return until is None

    def begin(self):
        self.heist.poll()
        self.now += STILL_S+.1
        self.heist.poll()
        self.assertEqual(self.heist.state, 'sneak')

    def steal(self):
        self.begin()
        self.assertTrue(self.run_for(30, lambda: self.heist.state == 'run'))

    def test_it_waits_for_ten_still_seconds_every_time_and_nothing_else(self):
        self.heist.poll()
        self.now += STILL_S-1
        self.heist.poll()
        self.assertFalse(self.heist.active)
        self.pointer += C.QPoint(40, 0)             # the mouse moved: the count starts over
        self.now += 2
        self.heist.poll()
        self.assertFalse(self.heist.active)
        self.now += STILL_S
        self.heist.poll()
        self.assertTrue(self.heist.active)
        self.heist.abort()
        self.assertEqual(self.window.pos(), self.home)
        self.gear.pet.mood = 'idle'
        slept = []
        self.window.behavior = type('B', (), dict(quiet=False, sleeping=False, touched=lambda s: None,
                                                  sleep=lambda s: slept.append(self.now)))()
        self.now += STILL_S+1                        # the mouse never moved: no second game,
        self.heist.poll()
        self.assertFalse(self.heist.active)
        self.assertEqual(len(slept), 1)              # it dozes instead
        self.now += 600
        self.heist.poll()
        self.assertFalse(self.heist.active)          # ... for as long as nothing moves
        self.assertEqual(len(slept), 1)              # and it is sent to doze only the once
        self.pointer += C.QPoint(0, 30)              # the mouse moves, then rests again
        self.heist.poll()
        self.now += STILL_S-1
        self.heist.poll()
        self.assertFalse(self.heist.active)
        self.now += 1.5                              # ten seconds, no cool-down beyond that
        self.heist.poll()
        self.assertTrue(self.heist.active)
        self.heist.abort()
        del self.window.behavior
        self.gear.pet.mood = 'idle'
        self.pointer += C.QPoint(0, 30)
        self.heist.poll()
        self.gear.origin = C.QPoint(3, 3)            # a hand is holding it: never then
        self.now += STILL_S+1
        self.heist.poll()
        self.assertFalse(self.heist.active)
        self.gear.origin = None
        self.heist.poll()
        self.assertTrue(self.heist.active)
        self.gear.origin = C.QPoint(3, 3)            # ... and a hand on it ends a game under way
        self.run_for(.1)
        self.assertFalse(self.heist.active)
        self.gear.origin = None

    def test_it_does_not_start_when_it_should_not(self):
        for block in ('disabled', 'quiet', 'matching', 'doll'):
            if block == 'disabled': self.heist.enabled = False
            if block == 'matching': self.gear.matching = True
            if block == 'quiet':
                self.window.behavior = type('B', (), dict(quiet=True, sleeping=False, touched=lambda s: None))()
            if block == 'doll': self.gear.set_skin('doll')
            self.heist.poll(); self.now += STILL_S+1; self.heist.poll()
            self.assertFalse(self.heist.active, block)
            self.heist.enabled = True; self.gear.matching = False
            if hasattr(self.window, 'behavior'): del self.window.behavior
            self.gear.set_skin('puppet')

    def test_it_freezes_when_watched_then_takes_the_pointer_and_runs(self):
        self.begin()
        self.assertEqual(self.heist.sprite.mode, 'arrow')
        self.run_for(.5)
        self.assertEqual(self.gear.pet.mood, 'sneak')
        self.assertEqual(self.gear.pet.facing, 1)          # the pointer is to its left
        before = self.window.pos()
        self.pointer += C.QPoint(0, 12)
        self.run_for(.5)
        self.assertEqual(self.gear.pet.mood, 'freeze')
        self.assertLess((self.window.pos()-before).manhattanLength(), 4)
        self.assertTrue(self.run_for(30, lambda: self.heist.state == 'run'))
        self.assertTrue(self.gear.pet.carrying)
        self.assertEqual(self.heist.sprite.mode, 'cross')
        start = self.window.x()
        self.run_for(.6)
        self.assertGreater(self.window.x(), start+100)     # away from the pointer
        self.assertEqual(self.gear.pet.facing, -1)
        self.assertEqual(self.gear.pet.mood, 'run')

    def test_a_click_trips_it_and_shooting_the_sack_starts_the_begging(self):
        self.steal()
        self.run_for(.9)
        self.inputs.left = True
        self.run_for(.05)
        self.inputs.left = False
        self.assertEqual(self.heist.state, 'trip')
        self.assertFalse(self.gear.pet.has_sack)
        self.assertTrue(self.heist.sack.isVisible())
        self.run_for(1.2)
        self.assertEqual(self.heist.state, 'down')
        self.assertTrue(self.heist.sack.targetable())
        self.heist.sack_hit()
        self.assertIsNotNone(self.heist.loot)
        self.assertFalse(self.gear.pet.carrying)
        self.assertFalse(self.heist.sack.targetable())
        self.assertEqual(self.heist.sack.phase, 'burst')           # the 辞章 shows over the sack
        self.assertTrue(self.run_for(6, lambda: self.heist.state == 'cry'))
        self.assertTrue(self.heist.sprite.leaving)                 # ... the sight is gone,
        self.assertFalse(hasattr(self.heist.sprite, 'relic'))      # and nothing rides the pointer
        self.assertTrue(self.run_for(60, lambda: self.heist.state == 'hit'))
        self.run_for(.05)
        self.assertEqual(self.gear.pet.mood, 'hit')
        self.pointer += C.QPoint(0, 160)                   # pull it away: it follows again
        self.run_for(.1)
        self.assertEqual(self.heist.state, 'cry')
        self.heist.pet_clicked()                           # hand it back
        self.assertEqual(self.heist.state, 'rejoice')
        self.assertTrue(self.gear.pet.has_sack)
        self.assertTrue(self.run_for(60, lambda: not self.heist.active))
        self.assertEqual(self.window.pos(), self.home)
        self.assertEqual(self.gear.pet.facing, 1)
        self.assertFalse(self.heist.sprite.isVisible())

    def test_unanswered_falls_end_with_it_walking_home_and_returning_the_pointer(self):
        self.steal()
        self.pointer = C.QPoint(self.area.left()+5, self.area.top()+5)
        falls = []
        def watch():
            if self.heist.state == 'trip' and (not falls or falls[-1] != self.heist.falls):
                falls.append(self.heist.falls)
            return not self.heist.active
        self.assertTrue(self.run_for(240, watch))
        self.assertEqual(falls, [1, 2, 3])
        self.assertEqual(self.window.pos(), self.home)
        self.assertFalse(self.gear.pet.carrying)
        self.assertTrue(self.gear.pet.has_sack)

    def test_escape_and_work_end_it_at_once(self):
        self.steal()
        self.run_for(.4)
        self.assertNotEqual(self.window.pos(), self.home)
        self.inputs.escape = True
        self.run_for(.05)
        self.inputs.escape = False
        self.assertFalse(self.heist.active)
        self.assertEqual(self.window.pos(), self.home)
        self.assertFalse(self.gear.pet.carrying)
        self.assertTrue(self.gear.pet.has_sack)
        self.assertNotIn(self.gear.pet.mood, ('run', 'sneak'))
        self.gear.pet.mood = 'idle'                 # the landing bounce has played out
        self.pointer += C.QPoint(0, 30)             # the mouse stirred, so another game may come
        self.steal()
        self.gear.set_matching(True)
        self.assertFalse(self.heist.active)
        self.assertEqual(self.window.pos(), self.home)
        self.gear.set_matching(False)

    def test_touching_it_with_the_pointer_trips_it_and_it_stays_on_screen(self):
        self.steal()
        self.run_for(.9)
        self.pointer = self.gear.mapToGlobal(self.gear.rect().center())
        self.run_for(.05)
        self.assertEqual(self.heist.state, 'trip')
        frame = C.QRect(self.gear.mapToGlobal(C.QPoint(0, 0)), self.gear.size())
        self.assertTrue(self.area.contains(frame))

    def test_a_purple_and_a_blue_every_time_and_a_third_three_times_in_ten(self):
        relics = load_relics()
        self.assertEqual(len(relics), 55)
        self.assertEqual({item['quality'] for item in relics}, set(COMMON) | set(RARE))
        self.assertEqual(set(TIERS), set(heist_module.QUALITY_GLOW))
        rng = random.Random(3)
        seen, extra = set(), 0
        for _ in range(4000):
            loot = pick_loot(relics, rng)
            self.assertEqual([item['quality'] for item in loot[:2]], ['奇珍', '独特'])
            seen.update(item['name'] for item in loot[:2])
            if len(loot) > 2:
                self.assertEqual(len(loot), 3)
                self.assertIn(loot[2]['quality'], RARE)
                extra += 1
        self.assertEqual(seen, {item['name'] for item in relics if item['quality'] in COMMON})
        self.assertAlmostEqual(extra/4000, RARE_CHANCE, delta=.03)
        self.assertEqual(pick_loot([], rng), [])

    def test_the_third_relic_has_a_floor_that_luck_resets(self):
        relics = load_relics()
        self.assertEqual(dict(PITY), {'穆修拉之核': 20, '被诅咒的蓝宝石': 10})

        class Never:                                    # no luck at all
            def choice(self, pool): return pool[0]
            def random(self): return .99
        pity = new_pity()
        thirds = []
        for _ in range(40):
            loot = pick_loot(relics, Never(), pity)
            self.assertEqual([item['quality'] for item in loot[:2]], ['奇珍', '独特'])
            thirds.append(loot[2]['name'] if len(loot) > 2 else None)
        # the necklace on the 10th; on the 20th the core wins and the
        # necklace, also due, follows with the next sack
        expected = {10: '被诅咒的蓝宝石', 20: '穆修拉之核', 21: '被诅咒的蓝宝石', 31: '被诅咒的蓝宝石', 40: '穆修拉之核'}
        self.assertEqual({i+1: name for i, name in enumerate(thirds) if name}, expected)

        class Lucky:                                    # the necklace by chance on the 4th sack
            def __init__(self): self.calls = 0
            def choice(self, pool):
                named = [item for item in pool if item['name'] == '被诅咒的蓝宝石']
                return named[0] if named else pool[0]
            def random(self):
                self.calls += 1
                return .0 if self.calls == 4 else .99
        pity = new_pity()
        thirds = []
        rng = Lucky()
        for _ in range(15):
            loot = pick_loot(relics, rng, pity)
            thirds.append(loot[2]['name'] if len(loot) > 2 else None)
        self.assertEqual([i+1 for i, name in enumerate(thirds) if name == '被诅咒的蓝宝石'], [4, 14])
        self.assertEqual(pity['穆修拉之核'], 15)             # the other count is untouched
        self.assertEqual(new_pity({'穆修拉之核': 7, '被诅咒的蓝宝石': 99, 'x': 1}), {'穆修拉之核': 7, '被诅咒的蓝宝石': 10})
        self.assertEqual(new_pity('nonsense'), {'穆修拉之核': 0, '被诅咒的蓝宝石': 0})

    def test_one_tear_at_a_time_on_a_parabola_to_the_ground(self):
        from mapmatching.appearance.skins.puppet.effects import tear_position
        points = [tear_position(i/40, 1) for i in range(41)]
        self.assertAlmostEqual(points[-1][1], puppet.GROUND_Y)
        self.assertLess(min(y for _, y in points), points[0][1])           # up first, then down
        xs = [x for x, _ in points]
        self.assertEqual(xs, sorted(xs))
        second = [points[i+1][1]-2*points[i][1]+points[i-1][1] for i in range(1, 40)]
        self.assertLess(max(second)-min(second), 1e-6)                     # constant curvature: a parabola
        self.assertLess(tear_position(.5, -1)[0], tear_position(0, -1)[0])

if __name__ == '__main__':
    unittest.main()
