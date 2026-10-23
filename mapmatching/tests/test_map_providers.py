"""Provider isolation, original integrity, floor masks and rendering regressions."""
import hashlib,json,unittest
from pathlib import Path
import cv2,numpy as np
from mapmatching.src.context import SessionContext
from mapmatching.src.reference import load,read_image
from mapmatching.src.map_style import floor_selection,zhanshi_mask
from mapmatching.src.live import raw_layer
from mapmatching.src.types import Candidate,Pose
ROOT=Path(__file__).resolve().parents[2]

class ProviderTests(unittest.TestCase):
 def test_context_and_isolation(self):
  with self.assertRaises(ValueError):SessionContext('nightmare','full')
  with self.assertRaises(ValueError):SessionContext('hard',None,'zhanshi')
  SessionContext('nightmare','full','zhanshi')
  SessionContext('hard','full','zhanshi')
  refs=load(ROOT/'maps',difficulty='nightmare',mode='solo')
  self.assertEqual(len(refs),27)
  self.assertTrue(all(not r.map_id.startswith('zhanshi/') for r in refs))
  for mode,count in [('full',28),('speed',27)]:
   refs=load(ROOT/'maps',difficulty='nightmare',mode=mode,provider='zhanshi')
   self.assertEqual(len(refs),count)
   self.assertTrue(all(r.map_id.startswith('zhanshi/') for r in refs))
 def test_sources_and_floor_regions(self):
  entries=json.loads((ROOT/'maps/floors.json').read_text(encoding='utf8'))['references']
  for e in entries:
   self.assertEqual(hashlib.sha256((ROOT/e['source']).read_bytes()).hexdigest(),e['sha256'])
   if e.get('provider')!='zhanshi':continue
   self.assertEqual({r['floor'] for r in e['regions']},{1,2} if e['difficulty']=='hard' else {1,2,-1})
   masks=[floor_selection((round(e['size'][1]*1000/e['size'][0]),1000),r,1000/e['size'][0]).astype(bool) for r in e['regions']]
   self.assertTrue(all(m.sum()>1000 for m in masks))
   # Display margins may overlap; no floor geometry may leak through.
   self.assertTrue(all((masks[i]&masks[j]).sum()<350 for i in range(len(masks)) for j in range(i)))
 def test_lazy_author_keeps_only_selected_evidence(self):
  from mapmatching.src.author_matcher import LazyAuthorAtlas
  from mapmatching.src.matcher import MapMatcher
  atlas=LazyAuthorAtlas(ROOT/'maps',MapMatcher,difficulty='nightmare',mode='full',provider='zhanshi')
  self.assertEqual(len(atlas.references),28)
  self.assertTrue(all(r.evidence is None for r in atlas.references))
  first,second=[r.map_id for r in atlas.references[:2]]
  atlas.ensure(first)
  self.assertEqual([r.map_id for r in atlas.references if r.evidence is not None],[first])
  atlas.ensure(second)
  self.assertEqual([r.map_id for r in atlas.references if r.evidence is not None],[second])
  self.assertEqual({r.recognition_map_id for r in atlas.references},{r.recognition_map_id for r in load(ROOT/'maps',difficulty='nightmare',mode='full',provider='zhanshi')})
 def test_conflicting_drawings_do_not_choose_higher_score(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  from mapmatching.src.author_matcher import TerrainIdentityMatcher
  from mapmatching.src.matcher import MatchResult
  solo_refs=[SimpleNamespace(map_id='solo/a',terrain_id='a'),SimpleNamespace(map_id='solo/b',terrain_id='b')]
  duo_refs=[SimpleNamespace(map_id='duo/a',terrain_id='a')]
  duo=SimpleNamespace(references=duo_refs,match=Mock(return_value=MatchResult(candidates=[Candidate('duo/a','nightmare','duo',10,Pose(1,1,1),.99,.01,1)])))
  solo=SimpleNamespace(references=solo_refs,match=Mock(return_value=MatchResult(candidates=[Candidate('solo/b','nightmare','solo',10,Pose(1,1,1),.85,.1,1)])))
  factory=lambda index,**kw:duo if kw['mode']=='duo' else solo
  result=TerrainIdentityMatcher(ROOT/'maps',factory).match(np.zeros((10,10,3),np.uint8))
  self.assertFalse(result.candidates)
  self.assertEqual(result.reason,'conflicting_reference_drawings')
 def test_author_coordinates_are_independent(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  from mapmatching.src.author_matcher import AuthorRouteMatcher
  from mapmatching.src.matcher import MatchResult
  original=Candidate('canonical','nightmare','solo',10,Pose(10,900,800),.9,.1,1)
  selected=Candidate('chosen','nightmare','full',10,Pose(.3,30,40),.9,.1,1)
  ref=SimpleNamespace(map_id='chosen',recognition_map_id='canonical',terrain_id='shared')
  primary=Mock(references=[ref]);primary.register_known.return_value=MatchResult(candidates=[selected])
  recognizer=Mock(references=[SimpleNamespace(map_id='canonical',terrain_id='shared')])
  recognizer.match.return_value=MatchResult(candidates=[original])
  result=AuthorRouteMatcher(primary,recognizer).match(np.zeros((10,10,3),np.uint8))
  self.assertEqual(result.candidates[0].pose,selected.pose)
  self.assertNotEqual(result.candidates[0].pose,original.pose)
 def test_polygon_renderer(self):
  from types import SimpleNamespace
  region=dict(floor=2,bbox=[0,0,20,20],polygons=[[[2,2],[9,2],[9,9],[2,9]]])
  reference=SimpleNamespace(map_id='test',regions=[region],exclusions=[])
  candidate=Candidate('test','nightmare','full',10,Pose(1,0,0),floor=2)
  layer=raw_layer((20,20,3),np.full((20,20,3),120,np.uint8),reference,candidate)
  self.assertEqual(int(layer[5,5,3]),255);self.assertEqual(int(layer[15,15,3]),0)
if __name__=='__main__':unittest.main()
