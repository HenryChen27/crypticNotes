import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import numpy as np
import cv2
from mapmatching.src import mapstore
from mapmatching.src.map_admin import context_text, floor_text, list_maps, set_enabled
from mapmatching.src.map_library import add_map
from mapmatching.src.reference import load

REGIONS = [dict(floor=-1, bbox=[0, 0, 300, 240]), dict(floor=1, bbox=[0, 150, 300, 300])]


def register(root, name, mode='solo', marker=0):
    """真录一张图进去。`marker` 挪一下线条 —— 重复检查按像素比，
    两次调用给同一张图会被拒。"""
    image = np.zeros((300, 300, 3), np.uint8)
    image[40:220, 40:100] = 120
    image[150:220, 40:240] = 120
    if marker:
        image[5:15, 5:15] = marker
    source = root/f'{name}.png'
    cv2.imencode('.png', image)[1].tofile(source)
    return add_map(root, source, name, 'nightmare', mode, REGIONS)


def read_disabled(root):
    # 从没移除过任何一张时这个文件根本不存在 —— 那是正常状态，不是错误。
    return mapstore.read_disabled(root/'maps')


class CatalogueTests(unittest.TestCase):
    def test_lists_active_and_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '留下的')
            register(root, '移除的', marker=60)
            set_enabled(root, 'nightmare/solo/移除的', False)
            rows = list_maps(root)
            by_id = {r['map_id']: r for r in rows}
            self.assertEqual(len(rows), 2)
            self.assertEqual(by_id['nightmare/solo/留下的']['state'], 'active')
            self.assertEqual(by_id['nightmare/solo/移除的']['state'], 'disabled')
            self.assertEqual(by_id['nightmare/solo/留下的']['name'], '留下的')
            self.assertEqual(by_id['nightmare/solo/留下的']['floors'], [1, -1])
            # 内置和自建不再区分：两边都没有 origin 这个键了
            self.assertNotIn('origin', by_id['nightmare/solo/留下的'])
            self.assertTrue(by_id['nightmare/solo/留下的']['writable'])

    def test_missing_index_flags_everything_stale(self):
        """索引还没建时列表照样能用，只是每一行都标成待重建 —— 不能崩。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '自建图')
            (root/'maps/index.json').unlink()
            rows = list_maps(root)
            self.assertEqual([r['name'] for r in rows], ['自建图'])
            self.assertTrue(rows[0]['stale'])

    def test_geometry_change_is_flagged_not_raised(self):
        """改了楼层框但没重建索引 → 那一行标 stale，`load()` 抛的是「重建索引」
        而不是别的什么看不懂的错。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '自建图')
            entries = mapstore.read_manifest(root/'maps')
            entries[0]['regions'] = [dict(floor=1, bbox=[0, 0, 300, 300])]
            mapstore.write_manifest(root/'maps', entries)
            self.assertTrue(list_maps(root)[0]['stale'])
            with self.assertRaisesRegex(ValueError, 'Rebuild index'):
                load(root/'maps')

    def test_text_helpers(self):
        self.assertEqual(floor_text([1, 2, -1]), '1F·2F·地下室')
        self.assertEqual(context_text('hard', None), '困难')
        self.assertEqual(context_text('nightmare', 'duo'), '噩梦·多人')


class RemovalTests(unittest.TestCase):
    def test_remove_drops_it_from_load_and_keeps_gates_intact(self):
        """最关键的一条：移除之后 load() 不抛异常，且返回集合里没有它。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '留下的')
            register(root, '移除的', marker=60)
            before = json.loads((root/'maps/index.json').read_text(encoding='utf-8'))
            set_enabled(root, 'nightmare/solo/移除的', False)
            after = json.loads((root/'maps/index.json').read_text(encoding='utf-8'))
            # index.json **一行都不用改**：load() 是按登记表走的，不在表里的
            # 条目自然不参与匹配。改它反而会逼出一次全量重建。
            self.assertEqual(before, after)
            loaded = load(root/'maps')
            self.assertEqual([r.map_id for r in loaded], ['nightmare/solo/留下的'])

    def test_source_image_and_evidence_are_left_alone(self):
        """软删除 = 搬条目。原图和特征都必须原地不动，恢复才是瞬时的。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '移除的')
            source = root/'maps/nightmare/solo/移除的.png'
            evidence = root/'maps/evidence'/mapstore.evidence_name('nightmare/solo/移除的')
            set_enabled(root, 'nightmare/solo/移除的', False)
            self.assertTrue(source.exists())
            self.assertTrue(evidence.exists())
            set_enabled(root, 'nightmare/solo/移除的', True)
            self.assertTrue(source.exists() and evidence.exists())

    def test_chinese_source_survives_a_roundtrip_byte_for_byte(self):
        """钉死 cp936 那个坑：write_text 不传 encoding 会把中文 source 写成乱码，
        而 source 只在读源图那一步被用到，症状是「文件明明在却报找不到」。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = register(root, '左 - 竖L门（09.10更新）')
            set_enabled(root, entry['map_id'], False)
            restored = set_enabled(root, entry['map_id'], True)
            self.assertEqual(restored, entry)
            raw = (root/'maps/floors.json').read_bytes()
            self.assertIn('左 - 竖L门（09.10更新）'.encode('utf-8'), raw)
            back = mapstore.read_manifest(root/'maps')[0]
            self.assertEqual(back['source'], entry['source'])
            self.assertEqual(load(root/'maps')[0].source, entry['source'])

    def test_restore_puts_it_back_and_clears_the_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '甲')
            register(root, '乙', marker=60)
            set_enabled(root, 'nightmare/solo/甲', False)
            set_enabled(root, 'nightmare/solo/甲', True)
            self.assertEqual(read_disabled(root), [])
            self.assertEqual(len(load(root/'maps')), 2)

    def test_restore_returns_it_to_its_original_row_not_the_end(self):
        """移除再恢复必须回到原来那一行。

        以前是 `entries+[stashed]`，追加到末尾 —— 用户看到的是「移除一下再恢复，
        这张图跑到列表最后去了」；而且 floors.json 的顺序变了，`index.json` 会跟着
        重排，并列候选的先后也跟着变。第一行/中间/最后一行三个位置各试一遍。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, name in enumerate(('甲', '乙', '丙')):
                register(root, name, marker=40+index)
            before = (root/'maps/floors.json').read_bytes()
            for name in ('甲', '丙', '乙'):
                map_id = f'nightmare/solo/{name}'
                at = [e['map_id'] for e in mapstore.read_manifest(root/'maps')].index(map_id)
                set_enabled(root, map_id, False)
                set_enabled(root, map_id, True)
                after = [e['map_id'] for e in mapstore.read_manifest(root/'maps')]
                self.assertEqual(after.index(map_id), at, f'{name} 没回到第 {at} 行')
                self.assertEqual((root/'maps/floors.json').read_bytes(), before)

    def test_position_of_a_map_removed_before_this_existed_is_simply_unknown(self):
        """老 `disabled.json` 没有 positions 字段 —— 不能因此报错，追加到末尾即可。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = register(root, '甲')
            register(root, '乙', marker=60)
            set_enabled(root, 'nightmare/solo/甲', False)
            payload = json.loads((root/'maps/disabled.json').read_text(encoding='utf-8'))
            payload.pop('positions')                     # 旧格式
            (root/'maps/disabled.json').write_text(
                json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(set_enabled(root, 'nightmare/solo/甲', True), entry)
            self.assertEqual(len(load(root/'maps')), 2)

    def test_a_crash_leaving_both_files_self_heals_to_active(self):
        """`set_map_enabled` 的写入顺序保证崩溃只会留下「两边都有」。

        这时以 floors.json 为准判成 active —— 自愈，而且列表里不能出现两行。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = register(root, '甲')
            set_enabled(root, 'nightmare/solo/甲', False)
            # 手工把条目也塞回 floors.json，模拟「写完了 disabled 就崩了」
            mapstore.write_manifest(root/'maps', [entry])
            rows = list_maps(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['state'], 'active')

    def test_unknown_id_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '甲')
            with self.assertRaises(ValueError):
                set_enabled(root, 'nightmare/solo/不存在', False)
            with self.assertRaises(ValueError):
                set_enabled(root, 'nightmare/solo/不存在', True)

    def test_restore_is_a_no_op_when_already_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = register(root, '甲')
            self.assertEqual(set_enabled(root, 'nightmare/solo/甲', True), entry)
            self.assertEqual(read_disabled(root), [])
            self.assertEqual(len(load(root/'maps')), 1)

    def test_read_only_directory_reports_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            register(root, '甲')
            with mock.patch('mapmatching.src.map_admin.os.access', return_value=False):
                with self.assertRaisesRegex(ValueError, '程序目录不可写'):
                    set_enabled(root, 'nightmare/solo/甲', False)


if __name__ == '__main__':
    unittest.main()
