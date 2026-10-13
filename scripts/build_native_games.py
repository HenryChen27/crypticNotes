"""Build tiny system-WebView launcher and a separate, unchanged game payload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
WEBVIEW_VERSION='1.0.3405.78'
GAME_VERSION='2.4.4'


def bundle(folder, target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(folder).as_posix())
                info.create_system=3;info.external_attr=path.stat().st_mode<<16
                info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,path.read_bytes())
    return {'version':GAME_VERSION,'size':target.stat().st_size,
        'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'url':'https://github.com/HenryChen27/Jellyfish/releases/download/desktop-v'+GAME_VERSION+'/'+target.name}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    key='windows-x64' if sys.platform=='win32' else 'macos-'+('arm64' if platform.machine()=='arm64' else 'x64')
    out=ROOT/'out/minigames-native';runtime=out/key
    runtime.mkdir(parents=True,exist_ok=True)
    if sys.platform=='win32':
        package=ROOT/'build/native-games'/('webview2-'+WEBVIEW_VERSION+'.nupkg')
        package.parent.mkdir(parents=True,exist_ok=True)
        if not package.exists():
            urllib.request.urlretrieve('https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/'+WEBVIEW_VERSION+'/microsoft.web.webview2.'+WEBVIEW_VERSION+'.nupkg',package)
        with zipfile.ZipFile(package) as z:
            for name in ('lib/net462/Microsoft.Web.WebView2.Core.dll','lib/net462/Microsoft.Web.WebView2.WinForms.dll',
                         'runtimes/win-x64/native/WebView2Loader.dll','LICENSE.txt'):
                (runtime/Path(name).name).write_bytes(z.read(name))
        compiler=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        # ICO container embeds the original PNG bytes; no game asset is altered.
        icon_png=(ROOT/'mapmatching/assets/minigames/fish5.png').read_bytes()
        iw,ih=struct.unpack('>II',icon_png[16:24])
        icon=ROOT/'build/native-games/GameLauncher.ico'
        (runtime/'GameLauncher.ico').unlink(missing_ok=True)
        icon.write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',iw if iw<256 else 0,ih if ih<256 else 0,0,0,1,32,len(icon_png),22)+icon_png)
        subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
            '/out:'+str(runtime/'GameLauncher.exe'),'/win32icon:'+str(icon),'/r:System.Windows.Forms.dll','/r:System.Drawing.dll',
            '/r:System.Web.Extensions.dll','/r:'+str(runtime/'Microsoft.Web.WebView2.Core.dll'),
            '/r:'+str(runtime/'Microsoft.Web.WebView2.WinForms.dll'),str(ROOT/'scripts/game_launcher/windows.cs')],check=True)
    else:
        app=runtime/'GameLauncher.app';binary=app/'Contents/MacOS/GameLauncher';binary.parent.mkdir(parents=True,exist_ok=True)
        arch = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
        subprocess.run(['swiftc','-O','-target',arch+'-apple-macos12.0',str(ROOT/'scripts/game_launcher/macos.swift'),'-o',str(binary),
                        '-framework','Cocoa','-framework','WebKit'],check=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'GameLauncher',
            'CFBundleIdentifier':'com.henrychen.minigames.launcher','CFBundleName':'小游戏',
            'CFBundlePackageType':'APPL','CFBundleVersion':'3','CFBundleShortVersionString':GAME_VERSION,
            'LSUIElement':True,'NSHighResolutionCapable':True}))
        import build_macos
        build_macos.BUNDLE_ID='com.henrychen.minigames.launcher'
        keychain=os.environ.get('MACOS_KEYCHAIN','');identity=build_macos.signing_identity(keychain)
        build_macos.sign(app,identity,keychain);build_macos.verify(app,identity)
    shutil.copy2(ROOT/'scripts/game_launcher/safe-exit.js',runtime/'safe-exit.js')
    shutil.copy2(ROOT/'scripts/game_launcher/host-audio.js',runtime/'host-audio.js')
    (runtime/'package.json').write_text(json.dumps({'id':'game-launcher','platform':key,'version':GAME_VERSION}),encoding='utf-8')
    game=out/'jellyfish';game.mkdir(parents=True,exist_ok=True)
    # The source is authoritative, including removed/replaced resources.
    payload=game/'game'
    if payload.exists():
        if payload.resolve().parent != (out/'jellyfish').resolve():
            raise RuntimeError('Unexpected payload path')
        shutil.rmtree(payload)
    hashes={}
    for name in ('index.html','assets','js','css'):
        source=args.source/name;target=game/'game'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.mp4','*.MP4'))
        else:shutil.copy2(source,target)
    # Check every copied byte, including all music, videos, fonts and images.
    for path in (game/'game').rglob('*'):
        if path.is_file():
            rel=path.relative_to(game/'game')
            if not (args.source/rel).is_file():
                if (ROOT/'games/jellyfish/overrides'/rel).is_file():continue
                raise RuntimeError('Unexpected stale game resource: '+str(rel))
            checksum=hashlib.sha256(path.read_bytes()).hexdigest()
            assert checksum==hashlib.sha256((args.source/rel).read_bytes()).hexdigest(),rel
            hashes[rel.as_posix()]=checksum
    (out/'game-resource-hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    # Use the upstream UI and save/record implementation without overrides.
    (game/'package.json').write_text(json.dumps({'id':'jellyfish','runtime':'system-webview','version':GAME_VERSION}),encoding='utf-8')
    catalog_path=out/'native-desktop-games.json'
    catalog=json.loads(catalog_path.read_text()) if catalog_path.exists() else {'schema':2,'id':'jellyfish','launchers':{}}
    catalog['launchers'][key]=bundle(runtime,out/('GameLauncher-'+key+'.zip'))
    catalog['game']=bundle(game,out/'Jellyfish-game.zip')
    catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Shared launcher:',catalog['launchers'][key]['size'],'bytes')
    print('Complete game resources:',catalog['game']['size'],'bytes; verified files:',len(hashes))


if __name__=='__main__':main()
