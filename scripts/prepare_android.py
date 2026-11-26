"""Stage unmodified matching core and registered maps for the Android package."""
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
target=ROOT/'android/generated'
python=target/'python/mapmatching'
python.mkdir(parents=True,exist_ok=True)
from mapmatching.module_payload import ASSETS, FILES, digest
for name in ('__init__.py','config.py','paths.py','pvp_package.py','module_payload.py'):
    shutil.copy2(ROOT/'mapmatching'/name,python/name)
for name in ('src','assets/map-ui','assets/mobile-map-ui'):
    shutil.copytree(ROOT/'mapmatching'/name,python/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
# Same font as the desktop client, so both clients read as one product.
# Only the UI face is staged; the italic accent face is desktop-only.
font=ROOT/'mapmatching/assets/fonts/DFPOP1-W5.ttf'
if font.exists():
    (target/'assets/fonts').mkdir(parents=True,exist_ok=True)
    shutil.copy2(font,target/'assets/fonts'/font.name)
for generated in (target/'assets/maps',target/'base-assets',python/'builtin/maps'):
    expected=ROOT/'android/generated'
    if generated.exists():
        if generated.resolve()!=generated or not generated.is_relative_to(expected):raise RuntimeError('Unexpected generated asset path')
        shutil.rmtree(generated)
assets=ROOT/'android/app/src/main/assets'
shutil.copytree(assets,target/'base-assets',ignore=shutil.ignore_patterns('pvp','pvp-*.json',*FILES['games']))
shutil.copy2(ROOT/'mapmatching/assets/update-news.json',target/'base-assets/update-news.json')
if '--local-review' in sys.argv:
    import json
    pins={}
    for key,name in ASSETS.items():
        path=ROOT/'release'/name
        pins[key]=dict(asset=name,size=path.stat().st_size,sha256=digest(path))
    (target/'base-assets/module-review.json').write_text(json.dumps(pins),encoding='utf8')
print('Staged host only; module payloads are separate downloads.')
