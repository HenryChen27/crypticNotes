import unittest
import cv2
import numpy as np
from mapmatching.src.context import SessionContext
from mapmatching.src.evidence import extract
from mapmatching.src.reference import Reference
from mapmatching.src.types import Candidate, Pose
from mapmatching.src.preview import render_preview


class ContextAndPreviewTests(unittest.TestCase):
    def test_nightmare_requires_explicit_party_mode(self):
        for args in [('nightmare',None),('hard','duo'),('unknown',None)]:
            with self.assertRaises(ValueError):
                SessionContext(*args)
        self.assertEqual(SessionContext('nightmare','duo').mode,'duo')

    def test_overlay_preserves_hud_and_excludes_other_floor(self):
        raw = np.full((120,100,3),(35,28,22),np.uint8)
        cv2.rectangle(raw,(20,20),(60,60),(100,83,76),-1)
        cv2.rectangle(raw,(70,80),(95,105),(100,83,76),-1)
        ev=extract(raw,reference=True,max_side=120)
        ref=Reference('test','hard',None,'synthetic',ev,np.zeros(ev.mask.shape,np.float32),
                      [{'floor':1,'bbox':[0,0,100,70]},{'floor':2,'bbox':[0,70,100,120]}],[])
        candidate=Candidate('test','hard',None,1.,pose=Pose(1.2,60.,40.),floor=1)
        screenshot=np.full((240,300,3),32,np.uint8)
        result,meta=render_preview(screenshot,raw,ref,candidate)
        self.assertGreater(meta['changed_pixels'],500)
        self.assertEqual(meta['outside_viewport_changed_pixels'],0)
        np.testing.assert_array_equal(result[136,156],screenshot[136,156])
        self.assertFalse(np.array_equal(result[88,108],screenshot[88,108]))

    def test_unresolved_floor_is_not_rendered(self):
        raw=np.full((100,100,3),80,np.uint8)
        ev=extract(raw,reference=True)
        ref=Reference('test','hard',None,'synthetic',ev,np.zeros(ev.mask.shape,np.float32))
        candidate=Candidate('test','hard',None,1.,pose=Pose(1.,0.,0.))
        with self.assertRaises(ValueError):
            render_preview(raw,raw,ref,candidate)


if __name__=='__main__':
    unittest.main()
