import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from mapmatching.src.live import centered_floor_layer


class CenteredFloorTests(unittest.TestCase):
    def test_centers_geometry_not_asymmetric_atlas_margins(self):
        mask=np.zeros((200,300),np.uint8)
        mask[20:80,180:240]=1
        ref=SimpleNamespace(map_id='known',difficulty='hard',mode=None,
            regions=[{'floor':2,'bbox':[0,0,300,200]}],
            evidence=SimpleNamespace(mask=mask,image_factor=1))
        with patch('mapmatching.src.live.raw_layer',return_value='layer') as render:
            self.assertEqual(centered_floor_layer((600,1000,3),None,ref,2,scale=2),'layer')
        pose=render.call_args.args[3].pose
        self.assertEqual(pose.scale*210+pose.tx,500)
        self.assertEqual(pose.scale*50+pose.ty,300)
        self.assertTrue(render.call_args.kwargs['full_view'])

if __name__=='__main__':
    unittest.main()
