"""「屏幕上没有地图」判定：真实截图回归 + 纯函数边界。

这个模块存在的理由是一次真实的误判：`ui.no_map_evidence` 最初只看 `live.py:34`
那道可靠性门，结果在「地图开着但还没探索」的画面上返回 True，助手弹出
「当前未打开地图」并准备退出状态 —— 而那正是用户最需要它别退出的时刻。

fixtures/nomap/ 里的三张是用户提供的真实截图（截屏时压到了 1999×1249，
角点数经实测对分辨率不敏感，见下）。两侧的数字都记在这里，改动阈值前先看它们。
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent/'fixtures/nomap'


def engine_details(image_name):
    """跑真实引擎，返回 (details, anchors, explained, contradiction)。"""
    import cv2
    from mapmatching.src.matcher import MapMatcher

    matcher = MapMatcher(ROOT/'maps', difficulty='hard', mode=None)
    image = cv2.imread(str(FIXTURES/image_name))
    assert image is not None, f'fixture missing: {image_name}'
    result = matcher.match(image)
    details = result.to_dict()
    top = details['candidates'][0] if details['candidates'] else None
    return (details, details['diagnostics'].get('anchors'),
            top and top['explained'], top and top['contradiction'])


class NoMapRealCaptureTest(unittest.TestCase):
    """真实截图：3D 游戏场景要判成「没有地图」，地图画面一律不许判成。"""

    @classmethod
    def setUpClass(cls):
        from mapmatching.ui import no_map_evidence
        cls.no_map = staticmethod(no_map_evidence)
        cls.measured = {}
        for name in ('game_world.jpg', 'map_empty_1.jpg', 'map_empty_2.jpg'):
            cls.measured[name] = engine_details(name)

    def test_anchors_separate_the_two_classes(self):
        """角点数是唯一分得开两类画面的信号，先把这条实测事实钉住。"""
        game = self.measured['game_world.jpg'][1]
        maps = [self.measured[n][1] for n in ('map_empty_1.jpg', 'map_empty_2.jpg')]
        self.assertGreater(game, 300, f'3D 场景角点数应 >300，实测 {game}')
        for anchors in maps:
            self.assertLess(anchors, 100, f'地图画面角点数应 <100，实测 {anchors}')
        self.assertGreater(game, max(maps)*3, '两类之间应有量级差距')

    def test_reliability_gate_alone_cannot_separate_them(self):
        """钉住「只靠 explained 分不开」这个事实 —— 它是加角点关卡的唯一理由。

        「地图开着没探索」的 explained 比 3D 场景还低，所以任何 explained 阈值
        都会二选一地出错。
        """
        game = self.measured['game_world.jpg'][2]
        empty = self.measured['map_empty_1.jpg'][2]
        self.assertLess(empty, game,
                        f'前提变了：没探索的地图 explained={empty} 不再低于 3D 场景 {game}；'
                        '若如此，说明引擎行为已变，可以重新评估是否还需要角点关卡')

    def test_game_world_is_flagged_as_no_map(self):
        details = self.measured['game_world.jpg'][0]
        self.assertTrue(self.no_map(details), '3D 游戏画面必须判成「没有地图」')

    def test_empty_map_is_not_flagged(self):
        """用户报的误判：地图开着但没探索，绝不能判成「没有地图」。"""
        for name in ('map_empty_1.jpg', 'map_empty_2.jpg'):
            details = self.measured[name][0]
            self.assertFalse(self.no_map(details),
                             f'{name} 是开着的地图，不许判成「没有地图」')


class NoMapSignalTest(unittest.TestCase):
    """纯函数边界：不依赖图片，跑得快。"""

    def setUp(self):
        from mapmatching.ui import no_map_evidence, NO_MAP_ANCHORS
        self.no_map = no_map_evidence
        self.limit = NO_MAP_ANCHORS

    def scene(self, anchors, explained, contradiction, retrieval=5.0, pose=True, reason=None,
              candidates=True):
        top = {'map_id': 'hard/x', 'difficulty': 'hard', 'mode': None,
               'retrieval_score': retrieval, 'explained': explained,
               'contradiction': contradiction, 'floor': None,
               'pose': {'scale': 1.0, 'tx': 0.0, 'ty': 0.0} if pose else None}
        # 形状必须和线上一致：anchors 在 diagnostics 里，顶层只有 reason/candidates。
        details = {'reason': reason or 'uncalibrated_research_baseline',
                   'candidates': [top] if candidates else [],
                   'diagnostics': {'anchors': anchors}}
        return details

    def test_texture_gate_blocks_flat_screens(self):
        """角点不够 = 平面面板，无论引擎多不自信都不算「没有地图」。"""
        self.assertFalse(self.no_map(self.scene(self.limit-1, .10, .90)))
        self.assertTrue(self.no_map(self.scene(self.limit, .10, .90)))

    def test_zoomed_in_is_never_no_map(self):
        """放得太大：matcher 直接返回 insufficient_visible_structure，绝不据此退出。"""
        for anchors in (0, 3, 400):
            details = self.scene(anchors, .10, .90, reason='insufficient_visible_structure',
                                 candidates=False)
            self.assertFalse(self.no_map(details), f'anchors={anchors} 时不该判成没有地图')

    def test_reliability_gate_mirrors_live_py(self):
        """逐条复刻 live.py:34：pose / explained / contradiction / retrieval_score。"""
        good = (400, .76, .20)
        self.assertFalse(self.no_map(self.scene(*good)))
        self.assertTrue(self.no_map(self.scene(400, .54, .20)), 'explained<.55')
        self.assertTrue(self.no_map(self.scene(400, .76, .41)), 'contradiction>.40')
        self.assertTrue(self.no_map(self.scene(400, .76, None)), 'contradiction 缺失')
        self.assertTrue(self.no_map(self.scene(400, .76, .20, pose=False)), 'pose 缺失')
        self.assertTrue(self.no_map(self.scene(400, .76, .20, retrieval=3)), 'retrieval_score<4')

    def test_unconfirmed_floor_and_ambiguity_are_not_no_map(self):
        """地图明明在屏幕上，只是楼层/身份没定下来 —— 不能拿来当退出理由。"""
        self.assertFalse(self.no_map(self.scene(400, .76, .20)))
        details = self.scene(400, .76, .20)
        details['candidates'].append(dict(details['candidates'][0], map_id='hard/y',
                                          explained=.759))
        self.assertFalse(self.no_map(details))

    def test_empty_candidate_list_with_texture_is_no_map(self):
        self.assertTrue(self.no_map(self.scene(400, .1, .9, candidates=False)))

    def test_missing_details_is_not_no_map(self):
        self.assertFalse(self.no_map(None))
        self.assertFalse(self.no_map({}))


if __name__ == '__main__':
    unittest.main()
