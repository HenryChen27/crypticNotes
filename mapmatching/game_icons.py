"""One package convention for game lists, background badges and native launchers."""
from pathlib import Path
from .paths import ROOT,DATA_ROOT

def game_icon_candidates(store):
    folder=Path(getattr(store,'game_root',store.folder/'game'))
    preferred=folder/'assets/icon.png'
    if preferred.resolve().is_relative_to(folder.resolve()):yield preferred
    yield DATA_ROOT/'out/minigames/icons'/f'{store.game_id}.png'
    legacy=getattr(store,'icon',None)
    if legacy:yield Path(legacy)
    yield ROOT/'mapmatching/assets/minigames/icons'/f'{store.game_id}.png'
    yield ROOT/'mapmatching/assets/minigames/fish5.png'

def game_pixmap(store,size=96):
    from PySide6 import QtGui as G,QtCore as C
    for path in game_icon_candidates(store):
        try:
            if not path.is_file() or path.stat().st_size>4*1024*1024:continue
            reader=G.QImageReader(str(path));dimensions=reader.size()
            if dimensions.width()<=0 or dimensions.height()<=0 or max(dimensions.width(),dimensions.height())>8192:continue
            reader.setScaledSize(dimensions.scaled(size,size,C.Qt.KeepAspectRatio))
            image=reader.read()
            if not image.isNull():return G.QPixmap.fromImage(image)
        except OSError:continue
    return G.QPixmap()


def cache_catalog_icons(catalog):
    """Optional catalog icons are fetched on the existing background sync thread."""
    import hashlib,urllib.request,os
    for key,spec in catalog.get('games',{}).items():
        icon=spec.get('icon')
        if not isinstance(icon,dict) or not key or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in key):continue
        url=icon.get('url','');sha=icon.get('sha256','')
        if not url.startswith('https://github.com/HenryChen27/mini_games/releases/download/') or len(sha)!=64:continue
        target=DATA_ROOT/'out/minigames/icons'/f'{key}.png'
        try:
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==sha:continue
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CrypticNotes-game-icons'}),timeout=15) as response:data=response.read(4*1024*1024+1)
            if len(data)>4*1024*1024 or hashlib.sha256(data).hexdigest()!=sha:continue
            target.parent.mkdir(parents=True,exist_ok=True);pending=target.with_suffix('.pending');pending.write_bytes(data);os.replace(pending,target)
        except (OSError,ValueError):continue
