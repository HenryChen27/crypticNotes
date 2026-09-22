import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from mapmatching.src.map_visibility import inspect_map_ui, templates
from mapmatching.src.live import match_with_cache


class MapVisibilityTests(unittest.TestCase):
    def test_requires_both_controls_at_different_resolutions(self):
        screen=np.full((600,960,3),30,np.uint8)
        for name,x,y in [('close',890,60),('overview',810,505)]:
            t=templates()[name]
            screen[y:y+t.shape[0],x:x+t.shape[1]]=t[:,:,None]
        for size in [(960,600),(1920,1200),(2560,1600)]:
            self.assertTrue(inspect_map_ui(cv2.resize(screen,size))['visible'])
        screen[505:550,810:860]=30
        self.assertFalse(inspect_map_ui(screen)['visible'])

    def test_unconfirmed_screen_never_searches_or_uses_cache(self):
        matcher=Mock()
        with patch('mapmatching.src.map_visibility.inspect_map_ui',return_value={'visible':False}):
            result,candidate,_=match_with_cache(matcher,np.zeros((10,10,3),np.uint8),Mock(),require_map_ui=True)
        self.assertIsNone(candidate)
        self.assertEqual(result.reason,'map_ui_not_confirmed')
        matcher.match.assert_not_called()
        matcher.register_known.assert_not_called()
