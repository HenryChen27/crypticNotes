"""Source-only game registrations; never included in the download catalog."""
import json
from pathlib import Path
from .paths import FROZEN

class LocalGameStore:
    local = True
    def __init__(self, data_root, spec):
        self.game_id=spec['id']
        if not self.game_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in self.game_id):
            raise ValueError('Invalid local game id')
        self.title=spec['title']
        self.icon=Path(spec['icon']) if spec.get('icon') else None
        self.window_icon=Path(data_root)/'out/minigames-local/runtime/minesweeper.ico'
        self.folder=Path(spec['source']).resolve()
        self.game_root=self.folder
        self.launcher=Path(data_root)/'out/minigames-local/runtime/GameLauncher.exe'
    def entry(self):return self.launcher
    def installed(self):return (self.game_root/'index.html').is_file() and self.entry().is_file()
    def native(self):return True
    def size(self):return 0

def local_games(data_root):
    if FROZEN:return []
    path=Path(data_root)/'out/minigames-local/games.json'
    try:
        specs=json.loads(path.read_text(encoding='utf-8'))
        return [LocalGameStore(data_root,s) for s in specs]
    except (OSError,ValueError,KeyError,TypeError):
        return []


def set_window_icon(pid, icon_path):
    """Use the selected game's window icon without rebuilding the native launcher."""
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.LoadImageW.argtypes=[wintypes.HINSTANCE,wintypes.LPCWSTR,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    api.LoadImageW.restype=wintypes.HANDLE
    api.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    api.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    icon=api.LoadImageW(None,str(icon_path),1,0,0,0x10|0x40)
    if not icon:return
    @callback
    def visit(hwnd,unused):
        owner=wintypes.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid:
            api.SendMessageW(hwnd,0x80,0,int(icon));api.SendMessageW(hwnd,0x80,1,int(icon))
        return True
    api.EnumWindows.argtypes=[callback,wintypes.LPARAM]
    api.EnumWindows(visit,0)
    return icon
