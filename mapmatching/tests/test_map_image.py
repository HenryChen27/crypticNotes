"""Storage compression must preserve import geometry and reproducible recognition."""
import tempfile,unittest,hashlib,json
from pathlib import Path
import cv2,numpy as np
from mapmatching.src.map_image import compact,scale_entry_geometry,MAX_SIDE
from mapmatching.src.map_library import add_map
from mapmatching.src.mapstore import build_index,read_image,_image_evidence
from mapmatching.src.reference import load
from mapmatching.src.map_admin import delete_map
from mapmatching.src.provider_packages import change
from mapmatching.src.map_update import stamp

class CompactMapTests(unittest.TestCase):
 def fixture(self,root):
  image=np.zeros((3300,2400,3),np.uint8)
  image[100:950,100:650]=120;image[700:950,100:2100]=120
  image[1800:2900,400:950]=120;image[2600:2900,400:2100]=120
  path=root/'original.png';cv2.imencode('.png',image)[1].tofile(path)
  return path,image,[dict(floor=2,bbox=[0,0,2400,1650]),dict(floor=1,bbox=[0,1650,2400,3300])]
 def test_import_and_index_rebuild_keep_original_terrain(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source,image,regions=self.fixture(root);before=source.read_bytes()
   expected=_image_evidence(image,dict(regions=regions,include_regions=[r['bbox'] for r in regions]))
   e=add_map(root,source,'large','nightmare','solo',regions)
   self.assertEqual(source.read_bytes(),before)
   stored=read_image(root/e['source']);self.assertEqual(max(stored.shape[:2]),MAX_SIDE)
   self.assertLess((root/e['source']).stat().st_size,len(before))
   self.assertEqual(e['regions'][0]['bbox'][3],1024)
   for rebuild in (False,True):
    if rebuild:
     (root/'maps/index.json').unlink()
     for p in (root/'maps/evidence').glob('*.npz'):p.unlink()
     build_index(root/'maps')
    ref=load(root/'maps',difficulty='nightmare',mode='solo')[0]
    for field in ('mask','boundary','corners','descriptors','radii'):
     np.testing.assert_array_equal(getattr(ref.evidence,field),getattr(expected,field))
    self.assertAlmostEqual(ref.evidence.image_factor,expected.image_factor/e['storage']['resize'][1])
   with self.assertRaises(ValueError):add_map(root,source,'duplicate','hard',None,regions)
   delete_map(root,e['map_id']);self.assertFalse((root/e['source']).exists());self.assertFalse((root/e['recognition']['source']).exists())
 def test_package_install_rebuild_and_remove_include_terrain(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source,image,regions=self.fixture(root)
   package=root/'package';e=add_map(package,source,'large','nightmare','solo',regions);stamp(package/'maps')
   live=root/'installed';change(live,'lianghapi',package/'maps')
   terrain=live/e['recognition']['source'];self.assertTrue(terrain.exists())
   (live/'maps/index.json').unlink();build_index(live/'maps')
   self.assertEqual(len(load(live/'maps',difficulty='nightmare',mode='solo')),1)
   change(live,'lianghapi');self.assertFalse(terrain.exists())
 def test_polygons_exclusions_and_input_are_scaled_consistently(self):
  e=dict(regions=[dict(floor=1,bbox=[0,0,4000,2000],polygons=[[[0,0],[4000,0],[0,2000]]])],include_regions=[[0,0,4000,2000]],exclude_regions=[[100,200,300,400]])
  before=json.dumps(e);scaled=scale_entry_geometry(e,(.5,.5),(2000,1000))
  self.assertEqual(json.dumps(e),before);self.assertEqual(scaled['regions'][0]['polygons'][0][1],[2000,0]);self.assertEqual(scaled['exclude_regions'],[[50,100,150,200]])
 def test_failed_compressed_import_leaves_no_files(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);source=root/'empty.png';cv2.imencode('.png',np.zeros((3000,2500,3),np.uint8))[1].tofile(source)
   with self.assertRaises(ValueError):add_map(root,source,'empty','hard',None,[dict(floor=1,bbox=[0,0,2500,3000])])
   self.assertTrue(source.exists());self.assertFalse((root/'maps/.import.lock').exists())
   self.assertFalse(any((root/'maps').rglob('*.webp')));self.assertFalse(any((root/'maps/recognition-inputs').glob('*.png')))

if __name__=='__main__':unittest.main()
