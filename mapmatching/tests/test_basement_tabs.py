"""磷光症 floor buttons: a vertical −1…−4 column read by position of the highlight.

Fixtures are the button column cut from three real phone screenshots
(2000×900), pasted back onto a dark canvas at their original place; the rest
of the frame (map, HUD) is not needed by the reader and is not kept.
"""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from mapmatching.src.floor_tabs import inspect_basement_tabs, inspect_floor_tabs, BASEMENT_TABS

FIXTURES = Path(__file__).resolve().parent/'fixtures/linguang-tabs'
META = json.loads((FIXTURES/'meta.json').read_text(encoding='utf8'))


def frame(name, controls=False):
    """`controls` also pastes the close/overview buttons so the open-map gate passes."""
    width, height = META['frame_size']
    x0, y0, x1, y1 = META['crop']
    canvas = np.full((height, width, 3), META['background'], np.uint8)
    canvas[y0:y1, x0:x1] = cv2.imdecode(np.fromfile(str(FIXTURES/name), np.uint8), 1)
    if controls:
        for control, (a, b, c, d) in META['controls'].items():
            canvas[b:d, a:c] = cv2.imdecode(np.fromfile(str(FIXTURES/control), np.uint8), 1)
    return canvas


def swap_rows(pixels, a, b, x=(1660, 1732), size=78):
    """Move the highlight to another row by exchanging two button cells."""
    out = pixels.copy()
    cell_a, cell_b = out[a:a+size, x[0]:x[1]].copy(), out[b:b+size, x[0]:x[1]].copy()
    out[a:a+size, x[0]:x[1]] = cell_b
    out[b:b+size, x[0]:x[1]] = cell_a
    return out


def transformed(pixels):
    yield 'native', pixels
    for width in (1440, 1280, 960):
        yield f'w{width}', cv2.resize(pixels, (width, round(pixels.shape[0]*width/pixels.shape[1])), interpolation=cv2.INTER_AREA)
    yield 'x1.3', cv2.resize(pixels, None, fx=1.3, fy=1.3, interpolation=cv2.INTER_CUBIC)
    yield 'dark', np.clip(pixels.astype(np.float32)*.55, 0, 255).astype(np.uint8)
    yield 'jpeg', cv2.imdecode(cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 50])[1], 1)
    yield 'blur', cv2.GaussianBlur(pixels, (5, 5), 1.2)


class BasementTabsTests(unittest.TestCase):
    def test_real_columns_under_video_transforms(self):
        for name, floor in META['floors'].items():
            for label, pixels in transformed(frame(name)):
                with self.subTest(fixture=name, transform=label):
                    reading = inspect_basement_tabs(pixels)
                    self.assertEqual(reading['floor'], floor, reading)
                    self.assertEqual(reading['buttons'], [-1, -2, -3, -4])
                    self.assertEqual(reading['reader'], 'basement')

    def test_fourth_basement_reads_as_minus_four(self):
        # The fixture viewing −2 has its highlight at the second row (y≈198)
        # and the −4 label at the fourth (y≈342).
        pixels = swap_rows(frame('viewing-2.png'), 198, 342)
        self.assertEqual(inspect_basement_tabs(pixels)['floor'], -4)
        self.assertEqual(BASEMENT_TABS, 4)

    def test_incomplete_column_is_unknown_not_wrong(self):
        pixels = frame('viewing-3.png')
        pixels[120:200, 1600:1800] = META['background']        # erase the −1 row
        reading = inspect_basement_tabs(pixels)
        self.assertIsNone(reading['floor'])
        self.assertEqual(reading['reason'], 'incomplete_column')

    def test_two_highlights_or_no_label_is_unknown(self):
        pixels = frame('viewing-2.png')
        pixels[342:420, 1660:1732] = pixels[198:276, 1660:1732]  # second bright square
        self.assertIsNone(inspect_basement_tabs(pixels)['floor'])
        blank = frame('viewing-2.png')
        blank[198:276, 1660:1732] = 100                          # bright square, no label
        self.assertIsNone(inspect_basement_tabs(blank)['floor'])

    def test_readers_ignore_each_other(self):
        from mapmatching.tests.test_floor_tabs import tab_frame
        for floor in (-1, 1, 2):
            self.assertIsNone(inspect_basement_tabs(tab_frame(floor))['floor'])
        for name in META['floors']:
            self.assertIsNone(inspect_floor_tabs(frame(name))['floor'])
        self.assertIsNone(inspect_basement_tabs(np.full((900, 2000, 3), 120, np.uint8))['floor'])
        self.assertIsNone(inspect_basement_tabs(np.full((2000, 900, 3), 30, np.uint8))['floor'])

    def test_manual_reading_recovers_dark_tint(self):
        from mapmatching.src.manual_alignment import manual_floor_reading
        tinted = np.clip(frame('viewing-3.png').astype(np.float32)*.4, 0, 255).astype(np.uint8)
        self.assertEqual(manual_floor_reading(tinted, basement=True)['floor'], -3)
        self.assertIsNone(manual_floor_reading(tinted)['floor'])


def library(*floors):
    regions = [dict(floor=f, bbox=[0, 0, 10, 10]) for f in floors]
    matcher = SimpleNamespace(references=[SimpleNamespace(regions=regions, map_id='x')], floor_hint=None)
    matcher.match = lambda pixels: (_ for _ in ()).throw(AssertionError('search must not run'))
    return matcher


class LibraryWiringTests(unittest.TestCase):
    def test_reader_follows_library_floors(self):
        from mapmatching.src.live import tab_reader
        self.assertIs(tab_reader(library(-1, -2, -3)), inspect_basement_tabs)
        self.assertIs(tab_reader(library(1, 2)), inspect_floor_tabs)
        self.assertIs(tab_reader(library(-1, 1, 2)), inspect_floor_tabs)
        self.assertIsNone(tab_reader(library()))

    def test_undrawn_basement_is_refused_before_any_search(self):
        from mapmatching.src.live import match_with_cache
        pixels = swap_rows(frame('viewing-2.png'), 198, 342)
        result, candidate, message = match_with_cache(library(-1, -2, -3), pixels, floor_tabs=inspect_basement_tabs)
        self.assertIsNone(candidate)
        self.assertEqual(result.reason, 'floor_not_in_library')
        self.assertEqual(result.diagnostics['floor_tabs']['floor'], -4)
        self.assertIn('负4层', message)

    def test_basement_reading_is_recorded_for_manual_offers(self):
        from mapmatching.src.manual_alignment import basement_library
        self.assertTrue(basement_library(dict(diagnostics=dict(floor_tabs=dict(floor=-2, reader='basement')))))
        self.assertFalse(basement_library(dict(diagnostics=dict(floor_tabs=dict(floor=2, reason='digit_group_and_highlight')))))
        self.assertFalse(basement_library({}))


def pc_frame(view=None):
    """The PC client (16:9, ESC hint instead of a close cross) viewing −2, or
    `view` after moving the highlight to that floor's cell."""
    pc = META['pc']
    width, height = pc['frame_size']
    x0, y0, x1, y1 = pc['crop']
    canvas = np.full((height, width, 3), pc['background'], np.uint8)
    canvas[y0:y1, x0:x1] = cv2.imdecode(np.fromfile(str(FIXTURES/'pc-viewing-2.png'), np.uint8), 1)
    for control, (a, b, c, d) in pc['controls'].items():
        canvas[b:d, a:c] = cv2.imdecode(np.fromfile(str(FIXTURES/control), np.uint8), 1)
    if view is not None and view != pc['floor']:
        cells = pc['cells']
        canvas = swap_rows(canvas, cells['rows'][str(pc['floor'])], cells['rows'][str(view)], x=tuple(cells['x']), size=cells['size'])
    return canvas


class PcClientTests(unittest.TestCase):
    def test_pc_column_reads_every_floor(self):
        for view in (-1, -2, -3, -4):
            pixels = pc_frame(view)
            for label, sample in (('native', pixels), ('w1280', cv2.resize(pixels, (1280, 674), interpolation=cv2.INTER_AREA))):
                with self.subTest(view=view, transform=label):
                    reading = inspect_basement_tabs(sample)
                    self.assertEqual(reading['floor'], view, reading)

    def test_pc_map_gate_passes_through_the_column(self):
        # No close cross on the PC client: the overview control plus the
        # recognised basement column must open the gate.
        from mapmatching.src.map_visibility import inspect_map_ui
        gate = inspect_map_ui(pc_frame())
        self.assertTrue(gate['visible'], gate)
        self.assertEqual(gate['floor_tabs']['floor'], -2)
        self.assertLess(gate['scores']['close'], .75)

    def test_pc_undrawn_basement_is_refused(self):
        from mapmatching.src.live import match_with_cache
        result, candidate, message = match_with_cache(library(-1, -2, -3), pc_frame(-4), require_map_ui=True, floor_tabs=inspect_basement_tabs)
        self.assertIsNone(candidate)
        self.assertEqual(result.reason, 'floor_not_in_library')
        self.assertIn('负4层', message)


ROOT = Path(__file__).resolve().parents[2]
MAP_9 = 'linguang/zhanshi/nightmare/full/9'


def confirmed_on_minus_two():
    from mapmatching.src.types import Candidate, Pose
    return Candidate(MAP_9, 'nightmare', 'full', 21, Pose(.96, 63., 333.), explained=.74, contradiction=.15, floor=-2)


@unittest.skipUnless((ROOT/'maps/floors.json').exists(), 'needs the bundled 磷光症 atlas')
class CrossFloorTests(unittest.TestCase):
    """A map confirmed on −2; the player then views −3 (offer, then forced
    overlay) and −4 (not drawn: refused). Frames hold only the buttons, so no
    map structure can be registered and the forced overlay is the centered one."""

    def test_desktop_worker_offers_forces_and_refuses(self):
        import multiprocessing, threading
        from mapmatching.src.live import worker
        parent, child = multiprocessing.Pipe()
        thread = threading.Thread(target=worker, args=(child, ROOT, 'nightmare', 'full', 'zhanshi', 'linguang'), daemon=True)
        thread.start()
        self.assertEqual(parent.recv()[0], 'ready')
        confirmed = confirmed_on_minus_two()

        def ask(generation, pixels, options):
            parent.send((generation, pixels, confirmed, options))
            kind, (_, layer, message, candidate, _, details) = parent.recv()
            return layer, message, candidate, details
        try:
            view3 = frame('viewing-3.png', controls=True)
            layer, message, candidate, details = ask(1, view3, dict(source='screen', confirmed_candidate=confirmed))
            self.assertIsNone(candidate)
            self.assertEqual(details['diagnostics']['manual_offer'], dict(map_id=MAP_9, floor=-3))
            self.assertEqual(details['diagnostics']['floor_tabs']['reader'], 'basement')
            layer, message, candidate, details = ask(2, view3, dict(source='screen', confirmed_candidate=confirmed, force_floor=-3))
            self.assertIsNotNone(layer)
            self.assertEqual((candidate.map_id, candidate.floor), (MAP_9, -3))
            self.assertTrue(details['diagnostics'].get('manual_centered'))
            self.assertIn('手动居中显示', message)
            view4 = swap_rows(frame('viewing-2.png', controls=True), 200, 344, size=72)
            layer, message, candidate, details = ask(3, view4, dict(source='screen', confirmed_candidate=confirmed))
            self.assertIsNone(layer)
            self.assertEqual(details['reason'], 'floor_not_in_library')
            self.assertNotIn('manual_offer', details['diagnostics'])
            self.assertIn('负4层没有参考图', message)
        finally:
            parent.send(None)
            thread.join(timeout=10)

    def test_phone_bridge_offers_forces_and_refuses(self):
        import sys
        sys.path.insert(0, str(ROOT/'android/app/src/main/python'))
        import mobile_bridge as bridge
        import tempfile
        bridge.initialize(str(ROOT), 'nightmare', 'full', 'zhanshi', scene='linguang')
        bridge._cached = bridge._confirmed = confirmed_on_minus_two(); bridge._pending_candidate = None
        with tempfile.TemporaryDirectory() as folder:
            def ask(pixels, **options):
                data = cv2.imencode('.png', pixels)[1].tobytes()
                return json.loads(bridge.match(data, str(Path(folder)/'layer.png'), True, True, **options))
            view3 = frame('viewing-3.png', controls=True)
            result = ask(view3)
            self.assertFalse(result['ok'])
            self.assertEqual(result['manual_offer'], dict(map_id=MAP_9, floor=-3))
            result = ask(view3, force_floor=-3)
            self.assertTrue(result['ok'], result)
            self.assertEqual((result['map_id'], result['floor']), (MAP_9, -3))
            self.assertIn('手动居中显示', result['message'])
            result = ask(view3, force_floor=-3, viewed_floor=-3)      # floor from the native header
            self.assertTrue(result['ok'], result)
            view4 = swap_rows(frame('viewing-2.png', controls=True), 200, 344, size=72)
            result = ask(view4)
            self.assertFalse(result['ok'])
            self.assertEqual(result['details']['reason'], 'floor_not_in_library')
            self.assertIn('负4层没有参考图', result['message'])
        bridge._cached = bridge._confirmed = None


if __name__ == '__main__':
    unittest.main()
