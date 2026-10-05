"""Merge published maps with locally added maps before replacing a library."""
from pathlib import Path
import json
import os
import shutil
import uuid


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def stamp(maps):
    maps = Path(maps)
    entries = read(maps/'floors.json', {'references': []})['references']
    entries += read(maps/'disabled.json', {'records': []}).get('records', [])
    write(maps/'official-library.json', {
        'ids': sorted(e['map_id'] for e in entries),
        'files': sorted(p.relative_to(maps).as_posix() for p in maps.rglob('*')
                        if p.is_file() and p.name != 'official-library.json')})


def child(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise ValueError('Unsafe map path: ' + str(relative))
    return path


def merge(old, incoming):
    """incoming is a disposable staged maps directory, never the live library.

    Missing provenance on legacy installations is handled conservatively:
    unknown entries/files are retained, rather than guessed to be obsolete.
    """
    old, incoming = Path(old), Path(incoming)
    fresh = read(incoming/'floors.json', {'references': []})
    disabled = read(incoming/'disabled.json', {'records': []})
    published = fresh['references'] + disabled.get('records', [])
    ids = {e['map_id'] for e in published}
    files = [p.relative_to(incoming).as_posix() for p in incoming.rglob('*') if p.is_file()]
    previous = read(old/'official-library.json', {'ids': list(ids), 'files': files})
    official_ids = set(previous['ids'])
    old_active = read(old/'floors.json', {'references': []})['references']
    old_disabled = read(old/'disabled.json', {'records': []}).get('records', [])
    custom = [e for e in old_active + old_disabled if e['map_id'] not in official_ids]
    # Never silently overwrite a newly colliding user ID or source file.
    for entry in custom:
        if entry['map_id'] in ids or entry['source'] in {e['source'] for e in published}:
            raise ValueError('User map conflicts with published map: ' + entry['map_id'])
    official_files = set(previous['files'])
    metadata = {'floors.json', 'disabled.json', 'index.json', 'official-library.json'}
    for p in old.rglob('*'):
        if not p.is_file():
            continue
        relative = p.relative_to(old).as_posix()
        if relative in metadata or relative.startswith('evidence/') or relative in official_files:
            continue
        source, target = child(old, relative), child(incoming, relative)
        if target.exists():
            # Unregistered local files are still user data. Keep both copies.
            if source.read_bytes() == target.read_bytes():
                continue
            target = child(incoming, '_preserved/' + uuid.uuid4().hex + '/' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Registered sources are required even if an old official file list contains
    # the same path; failure aborts the staged update, leaving live data intact.
    for entry in custom:
        relative = Path(entry['source']).relative_to('maps').as_posix()
        source, target = child(old, relative), child(incoming, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    fresh['references'] += [e for e in old_active if e['map_id'] not in official_ids]
    disabled.setdefault('records', []).extend(e for e in old_disabled if e['map_id'] not in official_ids)
    write(incoming/'floors.json', fresh)
    write(incoming/'disabled.json', disabled)
    write(incoming/'official-library.json', {'ids': sorted(ids), 'files': files})
    if custom:
        from .mapstore import build_index
        build_index(incoming)


def install(root, assets):
    """Android: prepare beside the live maps, then swap with rollback."""
    root, assets = Path(root), Path(assets)
    stage_root = root / ('map-update-' + uuid.uuid4().hex)
    stage = stage_root/'maps'
    backup = root/'maps-update-backup'
    live = root/'maps'
    # Recover interruption between the two directory renames.
    if backup.exists() and not live.exists():
        os.replace(backup, live)
    try:
        shutil.copytree(assets, stage)
        merge(live, stage)
        if backup.exists():
            shutil.rmtree(backup)
        if live.exists():
            os.replace(live, backup)
        try:
            os.replace(stage, live)
        except BaseException:
            if backup.exists():
                os.replace(backup, live)
            raise
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
