"""Stage unmodified matching core and registered maps for the Android package."""
from pathlib import Path
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'android/generated'
python=target/'python/mapmatching'
python.mkdir(parents=True,exist_ok=True)
for name in ('__init__.py','config.py','paths.py'):
    shutil.copy2(ROOT/'mapmatching'/name,python/name)
for name in ('src','assets/map-ui'):
    shutil.copytree(ROOT/'mapmatching'/name,python/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
# Same font as the desktop client, so both clients read as one product.
# Only the UI face is staged; the italic accent face is desktop-only.
font=ROOT/'mapmatching/assets/fonts/HYDiWRGJ.ttf'
if font.exists():
    (target/'assets/fonts').mkdir(parents=True,exist_ok=True)
    shutil.copy2(font,target/'assets/fonts'/font.name)
maps=target/'assets/maps'
maps.mkdir(parents=True,exist_ok=True)
for name in ('floors.json','index.json'):
    shutil.copy2(ROOT/'maps'/name,maps/name)
entries=json.loads((ROOT/'maps/floors.json').read_text(encoding='utf-8'))['references']
for entry in entries:
    source=ROOT/entry['source']
    destination=target/'assets'/entry['source']
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)
shutil.copytree(ROOT/'maps/evidence',maps/'evidence',dirs_exist_ok=True)
print('Staged',len(entries),'maps and unchanged matching modules')
