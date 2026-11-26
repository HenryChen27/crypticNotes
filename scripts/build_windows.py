"""Build a self-contained Windows folder; never bundle developer state."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import importlib.util

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-dir',type=Path,help='Build a standalone test ZIP without changing release assets or manifests')
    preview=parser.parse_args().preview_dir
    if preview:
        preview=preview.resolve()
        if not any(root in preview.parents for root in (ROOT/'out/gray',ROOT/'out/review')):parser.error('Use a new directory under out/gray or out/review')
        spec=preview/'windows';spec.mkdir(parents=True,exist_ok=False)
        dist,work=spec/'dist',spec/'work'
    else:
        spec,dist,work=ROOT/'build',ROOT/'dist',ROOT/'build/pyinstaller'
    env=os.environ.copy()
    # Host Anaconda DLLs can shadow Windows ICU while PyInstaller resolves Qt
    # dependencies. Use this build interpreter and the Windows runtime only.
    windows=Path(env.get('SystemRoot',r'C:\Windows'))
    env['PATH']=os.pathsep.join(map(str,(Path(sys.executable).parent,
        windows/'System32',windows,windows/'System32/Wbem')))
    extras=[]
    if importlib.util.find_spec('PyInstaller') is None and (ROOT/'.build-deps').exists():
        extras.append(str(ROOT/'.build-deps'))
    if importlib.util.find_spec('PySide6') is None and (ROOT/'.ui-deps').exists():
        extras.append(str(ROOT/'.ui-deps'))
    env['PYTHONPATH']=os.pathsep.join([str(ROOT),*extras])
    if preview:
        env['PYINSTALLER_CONFIG_DIR']=str(spec/'cache')
    else:
        subprocess.run([sys.executable,'-m','mapmatching','build-index',
                        '--index',str(ROOT/'maps')],cwd=ROOT,env=env,check=True)
        from build_matching_module import build
        build()
    args=[sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir','--windowed',
          '--contents-directory','.','--name','IdentityVMapAssistant','--paths',str(ROOT),
          '--hidden-import','mapmatching.portable_check','--collect-all','windows_capture',
          '--distpath',str(dist),'--workpath',str(work),'--specpath',str(spec)]
    for p in extras:
        args+=['--paths',p]
    if preview and ROOT/'out/review' in preview.parents:
        from build_module_payloads import stage_review
        pins=stage_review(preview)
        args+=['--add-data',f'{pins}{os.pathsep}.']
    for module in ('torch','tensorflow','matplotlib','pandas','IPython','pytest','notebook','tkinter',
                   'PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtWebEngineQuick'):
        args+=['--exclude-module',module]
    # Official maps are delivered by the independently managed matching module.
    from app_assets import desktop_assets
    data=[*desktop_assets(),ROOT/'mapmatching/correct.png', ROOT/'docs/images',
          ROOT/'scripts/run.cmd',ROOT/'scripts/create_shortcut.ps1',ROOT/'README.md']
    data.extend(p for p in (ROOT/'mapmatching/appearance/skins').rglob('*')
                if p.is_file() and p.suffix.lower() in ('.png','.jpg','.webp','.json'))
    data.extend((ROOT/'mapmatching').glob('*.md'))
    data.extend(ROOT.glob('*.cmd'))
    for path in data:
        if path.exists():
            destination=path.relative_to(ROOT) if path.is_dir() else path.parent.relative_to(ROOT)
            args+=['--add-data',f'{path}{os.pathsep}{destination}']
    args.append(str(ROOT/'mapmatching/launch.py'))
    subprocess.run(args,cwd=ROOT,env=env,check=True)
    from finalize_release import finalize
    finalize(dist/'IdentityVMapAssistant',preview or ROOT/'release',write_manifests=not preview)


if __name__=='__main__': main()
