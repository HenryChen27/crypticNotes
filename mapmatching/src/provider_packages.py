"""Transactional author package install/remove, retaining other authors and personal maps."""
from pathlib import Path
import json,shutil,os,uuid,hashlib
from .map_update import read,write,child
from .mapstore import evidence_name,build_index
PROVIDERS=('lianghapi','zhanshi')

def validate(provider):
    if provider not in PROVIDERS:raise ValueError('Unknown map provider')

def entries(maps):return read(Path(maps)/'floors.json',{'references':[]}).get('references',[])

def installed(maps,provider):
    validate(provider);maps=Path(maps)
    return any(e.get('provider','lianghapi')==provider and child(maps.parent,e['source']).is_file() for e in entries(maps))

def change(root,provider,incoming=None,spec=None):
    validate(provider);root=Path(root).resolve();live=root/'maps'
    transaction=root/('.provider-'+uuid.uuid4().hex);stage=transaction/'maps';backup=root/'maps-provider-backup'
    if backup.exists() and not live.exists():os.replace(backup,live)
    try:
        if live.exists():shutil.copytree(live,stage)
        else:stage.mkdir(parents=True)
        current=entries(stage);disabled=read(stage/'disabled.json',{'records':[]}).get('records',[])
        provenance=read(stage/'official-library.json',{'ids':[],'files':[]})
        fresh=entries(incoming) if incoming else []
        if any(e.get('provider','lianghapi')!=provider for e in fresh):raise ValueError('Author package contains a different provider')
        for entry in fresh:
            source=child(Path(incoming).parent,entry['source'])
            if not source.is_file() or (entry.get('sha256') and hashlib.sha256(source.read_bytes()).hexdigest()!=entry['sha256']):raise ValueError('Author original missing or hash mismatch: '+entry['map_id'])
            if entry.get('recognition'):
                geometry=entry['recognition'];path=child(Path(incoming).parent,geometry['source'])
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=geometry.get('sha256'):
                    raise ValueError('Author terrain input missing or hash mismatch: '+entry['map_id'])
        fresh_ids={e['map_id'] for e in fresh};official=set(provenance.get('ids',[]))|fresh_ids
        removed=[e for e in current+disabled if e.get('provider','lianghapi')==provider and e['map_id'] in official]
        removed_ids={e['map_id'] for e in removed};removed_files=set()
        remaining=[e for e in current if e['map_id'] not in removed_ids]
        disabled=[e for e in disabled if e['map_id'] not in removed_ids]
        shared={e['source'] for e in remaining+disabled}
        shared.update(e['recognition']['source'] for e in remaining+disabled if e.get('recognition'))
        if provider!='zhanshi' and any(e.get('provider')=='zhanshi' for e in remaining+disabled):
            canonical=read(stage/'recognition/floors.json',{}).get('references',[])
            shared.update(e['recognition']['source'] for e in canonical if e.get('recognition'))
        for entry in removed:
            paths=[entry['source'].removeprefix('maps/'),'evidence/'+evidence_name(entry['map_id'])]
            if entry.get('recognition'):paths.append(entry['recognition']['source'].removeprefix('maps/'))
            for relative in paths:
                if 'maps/'+relative in shared:continue
                path=child(stage,relative)
                if path.is_file():path.unlink()
                removed_files.add(relative)
        index=read(stage/'index.json',{})
        records={e['map_id']:e for e in index.get('references',[]) if e['map_id'] not in removed_ids}
        files=set(provenance.get('files',[]))-removed_files
        if incoming:
            incoming=Path(incoming)
            for source in incoming.rglob('*'):
                if not source.is_file():continue
                relative=source.relative_to(incoming).as_posix()
                if relative in ('floors.json','index.json','disabled.json','official-library.json'):continue
                target=child(stage,relative);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target);files.add(relative)
            fresh_index=read(incoming/'index.json',{})
            if not index:index={k:v for k,v in fresh_index.items() if k!='references'}
            records.update({e['map_id']:e for e in fresh_index.get('references',[])})
            # A genuine personal map colliding with an official ID must not disappear.
            collision=[e for e in current if e['map_id'] in fresh_ids and e['map_id'] not in set(provenance.get('ids',[]))
                and e.get('sha256')!=next(f.get('sha256') for f in fresh if f['map_id']==e['map_id'])]
            if collision:raise ValueError('Personal map conflicts with author package: '+collision[0]['map_id'])
            remaining+=fresh
        if not any(e.get('provider','lianghapi')=='zhanshi' for e in remaining+disabled):
            common=stage/'recognition'
            if common.exists():shutil.rmtree(common)
            files={f for f in files if not f.startswith('recognition/')}
        receipt=stage/'packages'/f'{provider}.json'
        if incoming:
            receipt.parent.mkdir(exist_ok=True);write(receipt,spec or {'provider':provider});files.add('packages/'+provider+'.json')
        else:
            receipt.unlink(missing_ok=True);files.discard('packages/'+provider+'.json')
        write(stage/'floors.json',{'schema_version':2,'references':remaining})
        write(stage/'disabled.json',{'records':disabled})
        index['references']=list(records.values());write(stage/'index.json',index)
        write(stage/'official-library.json',{'ids':sorted((official-removed_ids)|fresh_ids),'files':sorted(files)})
        if remaining:build_index(stage)
        if backup.exists():shutil.rmtree(backup)
        if live.exists():os.replace(live,backup)
        try:os.replace(stage,live)
        except BaseException:
            if backup.exists():os.replace(backup,live)
            raise
        if backup.exists():shutil.rmtree(backup)
    finally:
        if transaction.exists():shutil.rmtree(transaction)
