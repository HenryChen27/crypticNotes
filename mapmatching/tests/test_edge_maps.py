import unittest
from pathlib import Path
import cv2
import numpy as np
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.reference import read_image
from mapmatching.src.live import presentation_candidate


class EdgeMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)
        cls.root = Path(__file__).resolve().parents[2]
        cls.hard = MapMatcher(cls.root/'maps', difficulty='hard')

    def test_reported_originals(self):
        files = sorted((self.root/'examples/new').glob('*.png'))
        if len(files) != 3:
            self.skipTest('User regression screenshots unavailable')
        solo = MapMatcher(self.root/'maps', difficulty='nightmare', mode='solo')
        for matcher,path,identity,floor in (
            (solo,files[0],'nightmare/solo/左 - 竖拐角楼梯门（09.17更新）',1),
            (self.hard,files[2],'hard/北-1门',2)):
            selected,_ = presentation_candidate(matcher.match(read_image(path)))
            self.assertIsNotNone(selected)
            self.assertEqual((selected.map_id,selected.floor),(identity,floor))

    def test_all_reference_features_stay_in_one_floor(self):
        for ref in self.hard.floor_references:
            self.assertEqual(len(ref.regions),1)
            x,y,X,Y=np.array(ref.regions[0]['bbox'])*ref.evidence.image_factor
            pts=ref.evidence.corners
            self.assertTrue(((pts[:,0]>=x)&(pts[:,0]<X)&(pts[:,1]>=y)&(pts[:,1]<Y)).all())

    def test_map_near_top_left_recovers_with_expanded_view(self):
        files=sorted((self.root/'examples/new').glob('*.png'))
        if len(files)!=3:
            self.skipTest('User regression screenshots unavailable')
        original=read_image(files[2])
        h,w=original.shape[:2]
        image=cv2.warpAffine(original,np.float32([[.32,0,0],[0,.32,0]]),(w,h))
        self.assertIsNone(presentation_candidate(self.hard._match_view(image))[0])
        result=self.hard.match(image)
        selected,_=presentation_candidate(result)
        self.assertIsNotNone(selected)
        self.assertEqual((selected.map_id,selected.floor),('hard/北-1门',2))
        self.assertTrue(result.diagnostics['full_view'])
        known = self.hard.register_known(image, 'hard/北-1门')
        aligned, _ = presentation_candidate(known)
        self.assertIsNotNone(aligned)
        self.assertEqual((aligned.map_id, aligned.floor), ('hard/北-1门', 2))
        self.assertTrue(known.diagnostics['full_view'])
        self.assertFalse(known.diagnostics['identity_search_performed'])

    def test_wrong_floor_tab_is_advisory_and_retries_all_floors(self):
        files=sorted((self.root/'examples/new').glob('*.png'))
        if len(files)!=3:
            self.skipTest('User regression screenshots unavailable')
        image=read_image(files[2])
        self.hard.floor_hint=1  # This regression screenshot is actually floor 2.
        try:
            result=self.hard.match(image)
            selected,_=presentation_candidate(result)
            self.assertIsNotNone(selected)
            self.assertEqual(selected.floor,2)
            self.assertEqual(result.diagnostics['pipeline_view'],'all_floors_retry')

            known=self.hard.register_known(image,selected.map_id)
            aligned,_=presentation_candidate(known)
            self.assertIsNotNone(aligned)
            self.assertEqual(aligned.floor,2)
            self.assertEqual(known.diagnostics['pipeline_view'],'cached_all_floors_retry')
        finally:
            self.hard.floor_hint=None

    def test_blank_frame_stays_rejected_after_expansion(self):
        result=self.hard.match(np.zeros((600,800,3),np.uint8))
        self.assertIsNone(presentation_candidate(result)[0])
        self.assertTrue(result.diagnostics['expanded_view_rejected'])
