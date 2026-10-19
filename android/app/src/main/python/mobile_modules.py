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
