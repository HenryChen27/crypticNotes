import json,tempfile,unittest,shutil
from pathlib import Path
from mapmatching.tests.test_map_library import _fixture,REGIONS
from mapmatching.src.map_library import add_map
from mapmatching.src.map_update import stamp
from mapmatching.src.mapstore import read_manifest,write_manifest,build_index
from mapmatching.src.provider_packages import change,installed

class ProviderPackageTests(unittest.TestCase):
 def package(self,root,name,provider,shift=0):
  root.mkdir();source,_=_fixture(root,name+'.png',shift)
  entry=add_map(root,source,name,'nightmare','solo',REGIONS)
  if provider=='zhanshi':
   entry.update(provider=provider,mode='full',map_id='zhanshi/nightmare/full/'+name)
   write_manifest(root/'maps',[entry]);build_index(root/'maps')
  stamp(root/'maps');return root/'maps'
 def test_authors_update_and_delete_independently_preserving_personal(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);live=root/'installed';a=self.package(root/'a','author-a','lianghapi');b=self.package(root/'b','author-b','zhanshi',8)
   change(live,'lianghapi',a,{'sha256':'a'})
   personal,_=_fixture(root,'personal.png',16)
   custom=add_map(live,personal,'personal','hard',None,[r for r in REGIONS if r['floor']!=-1])
   before=(live/custom['source']).read_bytes()
   change(live,'zhanshi',b,{'sha256':'b'})
   self.assertTrue(installed(live/'maps','lianghapi'));self.assertTrue(installed(live/'maps','zhanshi'))
   change(live,'lianghapi',a,{'sha256':'a2'})
   self.assertTrue(installed(live/'maps','zhanshi'))
   change(live,'lianghapi')
   self.assertTrue(installed(live/'maps','zhanshi'));self.assertEqual((live/custom['source']).read_bytes(),before)
   self.assertNotIn('nightmare/solo/author-a',{e['map_id'] for e in read_manifest(live/'maps')})
   change(live,'lianghapi',a)
   self.assertEqual(len(read_manifest(live/'maps')),3)
 def test_wrong_provider_payload_rolls_back(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);a=self.package(root/'a','author-a','lianghapi');live=root/'installed';change(live,'lianghapi',a)
   before=(live/'maps/floors.json').read_bytes()
   with self.assertRaises(ValueError):change(live,'zhanshi',a)
   self.assertEqual((live/'maps/floors.json').read_bytes(),before)
if __name__=='__main__':unittest.main()
