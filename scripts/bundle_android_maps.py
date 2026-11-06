"""Stage one game map's atlases inside the Android APK for a test build.

The phone normally downloads whole author packages from the release channel.
For a build that has to carry a map the channel does not have yet (磷光症),
this packs just that scene's entries -- display atlases, lossless recognition
inputs, evidence and their manifest/index records -- under
`android/generated/assets/bundled/<scene>.zip` plus a spec JSON. The app
merges it into the installed library on start when its hash differs from the
last installed one (`MatchingModuleStore.installBundled` ->
`mobile_modules.install_scene`); official author packages are left alone.
Without the asset the app behaves as before, so release builds omit this.

Usage: python scripts/bundle_android_maps.py linguang
"""
from pathlib import Path
import json, hashlib, zipfile, tempfile, shutil, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
TITLES = {'linguang': '磷光症', 'curse': '厄运之女'}


def package(scene, archive):
    from mapmatching.src.mapstore import write_json, build_index, entry_scene
    source = ROOT/'maps'
    build_index(source)
    manifest = json.loads((source/'floors.json').read_text(encoding='utf8'))
    index = json.loads((source/'index.json').read_text(encoding='utf8'))
    with tempfile.TemporaryDirectory(dir=ROOT/'out', prefix='bundle-package-') as temp:
        maps = Path(temp)/'maps'; maps.mkdir()
        selected = [e for e in manifest['references'] if entry_scene(e) == scene]
        if not selected: raise SystemExit(f'No registered maps for scene {scene}')
        ids = {e['map_id'] for e in selected}
        write_json(maps/'floors.json', dict(schema_version=2, scene=scene, references=selected))
        write_json(maps/'index.json', {**index, 'references': [e for e in index['references'] if e['map_id'] in ids]})
        for entry in selected:
            target = Path(temp)/entry['source']; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT/entry['source'], target)
            if entry.get('recognition'):
                relative = entry['recognition']['source']; target = Path(temp)/relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT/relative, target)
        for record in index['references']:
            if record['map_id'] in ids:
                target = maps/'evidence'/record['array']; target.parent.mkdir(exist_ok=True); shutil.copy2(source/'evidence'/record['array'], target)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(maps.rglob('*')):
                if p.is_file():
                    info = zipfile.ZipInfo(p.relative_to(Path(temp)).as_posix(), (1980, 1, 1, 0, 0, 0)); info.external_attr = 0o100644 << 16
                    z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    return dict(schema=2, id='mapmatching-scene', scene=scene, name=TITLES.get(scene, scene), asset=archive.name, bundled=True,
                size=archive.stat().st_size, sha256=sha, version='库-'+sha[:12], count=len(selected),
                providers=sorted({e.get('provider', 'lianghapi') for e in selected}),
                difficulties=sorted({e['difficulty'] for e in selected}))


def main(scene):
    out = ROOT/'android/generated/assets/bundled'
    if out.exists(): shutil.rmtree(out)
    spec = package(scene, out/f'{scene}.zip')
    (out/f'{scene}.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: spec[k] for k in ('scene', 'size', 'sha256', 'count', 'providers')}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'linguang')
