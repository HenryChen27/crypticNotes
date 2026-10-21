"""Build the independently downloadable official matching library."""
from pathlib import Path
import json,hashlib,zipfile,tempfile,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def build():
    from mapmatching.src.map_update import stamp
    out=ROOT/'release';out.mkdir(exist_ok=True)
    archive=out/'IdentityVMapAssistant-Matching.zip'
    with tempfile.TemporaryDirectory(dir=ROOT/'out',prefix='matching-package-') as temp:
        maps=Path(temp)/'maps';maps.mkdir()
        source=ROOT/'maps'
        for name in ('hard','nightmare','_unindexed','evidence','floors.json','index.json','disabled.json','README.md'):
            p=source/name
            if p.is_dir():shutil.copytree(p,maps/name)
            elif p.is_file():shutil.copy2(p,maps/name)
        stamp(maps)
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(maps.rglob('*')):
                if p.is_file():z.write(p,p.relative_to(Path(temp)).as_posix())
    spec={'schema':1,'id':'mapmatching','asset':archive.name,'url':'https://github.com/HenryChen27/crypticNotes/releases/download/desktop-update-20260919-05738cf/'+archive.name,'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    spec['version']='库-'+spec['sha256'][:12]
    (out/'matching-module.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    return archive
if __name__=='__main__':print(build())
