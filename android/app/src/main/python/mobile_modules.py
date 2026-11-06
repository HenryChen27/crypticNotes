"""Optional official map payload lifecycle; never erase personal maps."""
from pathlib import Path
import json,shutil,uuid
from mapmatching.src.map_update import merge,install as install_maps

def install(root,assets):
    root=Path(root);assets=Path(assets)
    saved=root/'module-user-data/mapmatching/maps'
    if not (root/'maps').exists() and saved.exists():merge(saved,assets)
    install_maps(root,assets)
    backup=root/'maps-update-backup'
    if backup.exists():shutil.rmtree(backup)

def remove(root):
    root=Path(root);old=root/'maps';saved=root/'module-user-data/mapmatching/maps'
    stage=root/('preserve-maps-'+uuid.uuid4().hex);stage.mkdir()
    try:
        (stage/'floors.json').write_text('{"references":[]}',encoding='utf-8')
        (stage/'disabled.json').write_text('{"records":[]}',encoding='utf-8')
        merge(old,stage)
        saved.parent.mkdir(parents=True,exist_ok=True)
        if saved.exists():shutil.rmtree(saved)
        stage.rename(saved)
        if old.exists():shutil.rmtree(old)
    finally:
        if stage.exists():shutil.rmtree(stage)


def install_scene(root,assets,scene,spec_json):
    """Merge one game map's atlases (a bundled test package) into the live library.

    Unlike an author package this never claims the whole provider: entries of
    this scene are replaced, everything else -- official packages, personal
    maps, provenance -- is left untouched, so a later author update neither
    removes nor is removed by these atlases.
    """
    from mapmatching.src.mapstore import write_json,build_index,entry_scene,evidence_name
    from mapmatching.src.map_update import read,child
    root=Path(root);live=root/'maps';incoming=Path(assets)
    fresh=read(incoming/'floors.json',{'references':[]})['references']
    if any(entry_scene(e)!=scene for e in fresh):raise ValueError('Scene package contains another map')
    fresh_index=read(incoming/'index.json',{})
    live.mkdir(parents=True,exist_ok=True)
    current=read(live/'floors.json',{'schema_version':2,'references':[]})
    index=read(live/'index.json',{})
    for entry in current.get('references',[]):
        if entry_scene(entry)==scene:
            for relative in [entry['source']]+([entry['recognition']['source']] if entry.get('recognition') else []):
                path=child(root,relative)
                if path.is_file() and not any(e['source']==relative or (e.get('recognition') or {}).get('source')==relative for e in fresh):path.unlink()
            old=live/'evidence'/evidence_name(entry['map_id'])
            if old.is_file():old.unlink()
    for source in incoming.rglob('*'):
        if not source.is_file():continue
        relative=source.relative_to(incoming).as_posix()   # relative to the maps/ directory
        if relative in ('floors.json','index.json'):continue
        target=child(live,relative);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    removed={e['map_id'] for e in current.get('references',[]) if entry_scene(e)==scene}
    kept=[e for e in current.get('references',[]) if e['map_id'] not in removed]
    write_json(live/'floors.json',{**current,'references':kept+fresh})
    if not index:index={k:v for k,v in fresh_index.items() if k!='references'}
    ids={e['map_id'] for e in fresh}
    records=[r for r in index.get('references',[]) if r.get('map_id') not in ids and r.get('map_id') not in removed]
    index['references']=records+[r for r in fresh_index.get('references',[]) if r.get('map_id') in ids]
    write_json(live/'index.json',index)
    build_index(live)
    receipt=live/'packages'/f'scene-{scene}.json';receipt.parent.mkdir(exist_ok=True)
    write_json(receipt,json.loads(spec_json))
    return len(fresh)

def install_provider(root,assets,provider,spec_json):
    from mapmatching.src.provider_packages import change
    change(root,provider,assets,json.loads(spec_json))

def remove_provider(root,provider):
    from mapmatching.src.provider_packages import change
    change(root,provider)
