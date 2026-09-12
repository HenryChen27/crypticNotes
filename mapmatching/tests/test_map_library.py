import tempfile
import unittest
from pathlib import Path
import json
import numpy as np
import cv2
from mapmatching.src import mapstore
from mapmatching.src.map_library import add_map, validate_regions
from mapmatching.src.reference import read_image, load


def _fixture(root, name='source.png', shift=0):
    """一张够大、够有结构的假地图：`extract()` 至少要能找出 4 个角，
    否则 `add_map` 会在抽特征那步直接拒收。`shift` 挪一下线条，
    好造出「另一张图」——重复检查是按像素比的，两次调用给一样的图会被拦下。"""
    image=np.zeros((300,300,3),np.uint8)
    image[40+shift:220,40:100]=120
    image[150:220,40+shift:240]=120
    source=root/name; cv2.imencode('.png',image)[1].tofile(source)
    return source,image


REGIONS=[dict(floor=-1,bbox=[0,0,300,240]),dict(floor=1,bbox=[0,150,300,300])]


class LibraryTests(unittest.TestCase):
    def test_register_roundtrip(self):
        """登记一张图 = 原图进 maps/<难度>/<人数>/ + floors.json 多一条 + 索引挂上。"""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,image=_fixture(root)
            entry=add_map(root,source,'地下通路','nightmare','duo',REGIONS)
            self.assertEqual(entry['map_id'],'nightmare/duo/地下通路')
            target=root/'maps/nightmare/duo/地下通路.png'
            # 原图是被**复制**过去的，且逐字节不变（重编码会让 benchmark 的
            # sha256 配对静默失效）。
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(),source.read_bytes())
            np.testing.assert_array_equal(read_image(target),image)
            manifest=mapstore.read_manifest(root/'maps')
            self.assertEqual([e['map_id'] for e in manifest],['nightmare/duo/地下通路'])
            # 手绘的楼层框一物二用：regions 给叠图，include_regions 给特征提取。
            self.assertEqual(manifest[0]['regions'],REGIONS)
            self.assertEqual(manifest[0]['include_regions'],[r['bbox'] for r in REGIONS])

    def test_registered_map_is_loadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,_=_fixture(root)
            add_map(root,source,'地下通路','nightmare','duo',REGIONS)
            mapstore.build_index(root/'maps')
            refs=load(root/'maps',difficulty='nightmare',mode='duo')
            self.assertEqual(len(refs),1)
            self.assertEqual(refs[0].regions,REGIONS)
            # 难度/人数之外的筛选不该看见它 —— 这一条同时证明它真的进了同一张索引表，
            # 而不是像以前那样被 load() 从 user_maps 目录额外 append 进来。
            self.assertEqual(load(root/'maps',difficulty='nightmare',mode='solo'),[])
            self.assertEqual(load(root/'maps',difficulty='hard'),[])

    def test_source_inside_maps_is_registered_in_place(self):
        """图已经躺在 maps/ 里（比如用户自己粘进去的）时，登记不该再复制一份。
        这正是 `_unindexed/` 那张图的路径：它得能被录进来，而不是被复制成第二份。"""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,image=_fixture(root)
            target=root/'maps/hard/悬空桌门.png'
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
            before=sorted(p.name for p in (root/'maps/hard').iterdir())
            add_map(root,target,'悬空桌门','hard',None,REGIONS)
            self.assertEqual(sorted(p.name for p in (root/'maps/hard').iterdir()),before)
            np.testing.assert_array_equal(read_image(target),image)

    def test_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,_=_fixture(root)
            add_map(root,source,'地下通路','nightmare','duo',REGIONS)
            # 同名
            with self.assertRaises(ValueError):
                add_map(root,source,'地下通路','nightmare','duo',REGIONS)
            # 同图不同名（按像素比，所以换个文件名也躲不过）
            with self.assertRaises(ValueError):
                add_map(root,source,'地下通路二号','nightmare','duo',REGIONS)
            # 换个模式也不行。以前这条检查只看同一个 difficulty+mode（那时内置和
            # 自建是两棵树），现在只有一棵库，同一张图挂两个模式等于两边都匹配到它。
            with self.assertRaises(ValueError):
                add_map(root,source,'地下通路','nightmare','solo',REGIONS)
            # 但**另一张**图在别的模式下当然可以录
            other,_=_fixture(root,'other.png',shift=7)
            add_map(root,other,'另一张','nightmare','solo',REGIONS)
            self.assertEqual(len(mapstore.read_manifest(root/'maps')),2)

    def test_lock_is_released_on_failure(self):
        """抽特征失败（这里用一个纯色、抽不出结构的图触发）之后必须把锁放掉，
        否则用户第二次录入会一直撞「另一个地图正在保存」。"""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            flat=root/'flat.png'; cv2.imencode('.png',np.zeros((300,300,3),np.uint8))[1].tofile(flat)
            with self.assertRaises(ValueError):
                add_map(root,flat,'纯色图','hard',None,REGIONS)
            self.assertFalse((root/'maps/.import.lock').exists())
            # 失败的那张不该留下半个文件或半条登记
            self.assertEqual(mapstore.read_manifest(root/'maps'),[])
            self.assertFalse((root/'maps/hard/纯色图.png').exists())

    def test_name_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,_=_fixture(root)
            for name in ['','   ','带/斜杠','带\\反斜杠','带\n换行','.隐藏','x'*61]:
                with self.assertRaises(ValueError):
                    add_map(root,source,name,'hard',None,REGIONS)

    def test_region_validation(self):
        for regions in [[],[dict(floor=1,bbox=[-1,0,100,100])],
                        [dict(floor=1,bbox=[0,0,100,100]),dict(floor=1,bbox=[100,0,200,100])]]:
            with self.assertRaises(ValueError):
                validate_regions(regions,300,300)


if __name__=='__main__':
    unittest.main()
