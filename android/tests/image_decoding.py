"""Desktop contract checks for Android-only reference fallback."""
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/src/main/python'))
import mobile_images

class ReferenceDecodeTests(unittest.TestCase):
    def test_supported_image_never_uses_android(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'map.png';cv2.imwrite(str(p),np.full((10,12,3),120,np.uint8))
            with patch.object(mobile_images,'_android_png',side_effect=AssertionError):
                self.assertEqual(mobile_images.read_image(p).shape,(10,12,3))
    def test_webp_falls_back_to_android_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'map.webp';p.write_bytes(b'RIFF0000WEBPtest')
            pixels=np.full((4,5,3),99,np.uint8)
            with patch.object(mobile_images.cv2,'imdecode',side_effect=[None,pixels]),patch.object(mobile_images,'_android_png',return_value=b'png') as native:
                np.testing.assert_array_equal(mobile_images.read_image(p),pixels)
                native.assert_called_once_with(p)
    def test_corrupt_other_format_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'map.png';p.write_bytes(b'broken')
            with patch.object(mobile_images,'_android_png',side_effect=AssertionError),self.assertRaises(ValueError):
                mobile_images.read_image(p)
if __name__=='__main__':unittest.main()
