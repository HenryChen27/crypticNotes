"""Stage unmodified matching core and registered maps for the Android package."""
from pathlib import Path
import json
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
target=ROOT/'android/generated'
python=target/'python/mapmatching'
python.mkdir(parents=True,exist_ok=True)
for name in ('__init__.py','config.py','paths.py'):
    shutil.copy2(ROOT/'mapmatching'/name,python/name)
for name in ('src','assets/map-ui'):
    shutil.copytree(ROOT/'mapmatching'/name,python/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
# Same font as the desktop client, so both clients read as one product.
# Only the UI face is staged; the italic accent face is desktop-only.
font=ROOT/'mapmatching/assets/fonts/DFPOP1-W5.ttf'
if font.exists():
    (target/'assets/fonts').mkdir(parents=True,exist_ok=True)
    shutil.copy2(font,target/'assets/fonts'/font.name)
maps=target/'assets/maps'
if maps.exists():
    if not maps.resolve().is_relative_to(target.resolve()):raise RuntimeError('Unexpected generated maps path')
    shutil.rmtree(maps)
print('Staged matching code and UI assets; official maps are an optional download')
