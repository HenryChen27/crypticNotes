"""Build independently installable author libraries with shared terrain evidence."""
from pathlib import Path
import json,hashlib,zipfile,tempfile,shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='https://github.com/HenryChen27/crypticNotes/releases/download/desktop-update-20260919-05738cf/'

def build():
 from mapmatching.src.map_update import stamp
 from mapmatching.src.mapstore import write_json,build_index
 out=ROOT/'release';out.mkdir(exist_ok=True);source=ROOT/'maps'
 build_index(source)
 manifest=json.loads((source/'floors.json').read_text(encoding='utf8'))
 index=json.loads((source/'index.json').read_text(encoding='utf8'))
 specs={}
 for provider,title in [('lianghapi','凉哈皮'),('zhanshi','展十')]:
  archive=out/f'IdentityVMapAssistant-Maps-{provider}.zip'
  with tempfile.TemporaryDirectory(dir=ROOT/'out',prefix='matching-package-') as temp:
   maps=Path(temp)/'maps';maps.mkdir()
   selected=[e for e in manifest['references'] if e.get('provider','lianghapi')==provider]
   ids={e['map_id'] for e in selected}
   write_json(maps/'floors.json',dict(schema_version=2,references=selected))
   write_json(maps/'index.json',{**index,'references':[e for e in index['references'] if e['map_id'] in ids]})
   write_json(maps/'disabled.json',dict(records=[]))
   for entry in selected:
    original=ROOT/entry['source'];target=Path(temp)/entry['source'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
    if entry.get('recognition'):
     relative=entry['recognition']['source'];target=Path(temp)/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
   for record in index['references']:
    if record['map_id'] in ids:
     target=maps/'evidence'/record['array'];target.parent.mkdir(exist_ok=True);shutil.copy2(source/'evidence'/record['array'],target)
   # Shared recognition descriptors contain no other author's original images.
   if provider=='zhanshi':
    canonical=[e for e in manifest['references'] if e.get('provider','lianghapi')=='lianghapi' and e['difficulty']=='nightmare']
    canonical_ids={e['map_id'] for e in canonical};common=maps/'recognition';common.mkdir()
    write_json(common/'floors.json',dict(schema_version=2,references=canonical))
    records=[e for e in index['references'] if e['map_id'] in canonical_ids]
    write_json(common/'index.json',{**index,'references':records})
    (common/'evidence').mkdir()
    for record in records:shutil.copy2(source/'evidence'/record['array'],common/'evidence'/record['array'])
    for entry in canonical:
     if entry.get('recognition'):
      relative=entry['recognition']['source'];target=Path(temp)/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
   for name in ('README.md','providers.json'):
    if (source/name).is_file():shutil.copy2(source/name,maps/name)
   stamp(maps)
   with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(maps.rglob('*')):
     if p.is_file():
      info=zipfile.ZipInfo(p.relative_to(Path(temp)).as_posix(),(1980,1,1,0,0,0));info.external_attr=0o100644<<16
      z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
  sha=hashlib.sha256(archive.read_bytes()).hexdigest()
  specs[provider]=dict(schema=2,id='mapmatching',provider=provider,name=title,asset=archive.name,url=BASE+archive.name,size=archive.stat().st_size,sha256=sha,version='库-'+sha[:12],count=len(selected),difficulties=sorted({e['difficulty'] for e in selected}))
 legacy=out/'IdentityVMapAssistant-Matching.zip';shutil.copy2(out/specs['lianghapi']['asset'],legacy)
 catalog={**specs['lianghapi'],'schema':2,'default':'lianghapi','providers':specs}
 (out/'matching-module.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
 return legacy
if __name__=='__main__':print(build())
