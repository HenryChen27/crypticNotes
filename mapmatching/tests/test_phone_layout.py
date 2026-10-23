import unittest
from unittest.mock import patch
import numpy as np
from mapmatching.src.phone_layout import phone_viewport

class PhoneLayoutTests(unittest.TestCase):
 def test_no_controls_no_phone_crop(self):
  self.assertIsNone(phone_viewport(np.zeros((100,240,3),np.uint8)))
 def test_crop_preserves_pixel_coordinates(self):
  original=np.full((100,240,3),123,np.uint8)
  with patch('mapmatching.src.phone_layout.inspect_map_ui',return_value={'visible':True}):
   result=phone_viewport(original)
  self.assertEqual(result.shape,original.shape)
  self.assertTrue(np.array_equal(result[12:87,98:206],original[12:87,98:206]))
  self.assertFalse(result[:12].any());self.assertFalse(result[:,:98].any())
  self.assertTrue(np.all(original==123))
 def test_portrait_and_invalid_inputs_not_classified(self):
  for value in [None,np.zeros((240,100,3),np.uint8),np.zeros((1,5,3),np.uint8)]:
   self.assertIsNone(phone_viewport(value))
