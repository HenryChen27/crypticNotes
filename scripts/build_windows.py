"""Build a self-contained Windows folder; never bundle developer state."""
from pathlib import Path
import os
import subprocess
import sys
import importlib.util

ROOT=Path(__file__).resolve().parents[1]


def main():
    env=os.environ.copy()
    extras=[]
    if importlib.util.find_spec('PyInstaller') is None and (ROOT/'.build-deps').exists():
        extras.append(str(ROOT/'.build-deps'))
    if importlib.util.find_spec('PySide6') is None and (ROOT/'.ui-deps').exists():
        extras.append(str(ROOT/'.ui-deps'))
    env['PYTHONPATH']=os.pathsep.join([str(ROOT),*extras])
    subprocess.run([sys.executable,'-m','mapmatching','build-index',
                    '--index',str(ROOT/'maps')],cwd=ROOT,env=env,check=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
          '--contents-directory','.','--name','IdentityVMapAssistant','--paths',str(ROOT),
          '--hidden-import','mapmatching.portable_check',
          '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build/pyinstaller'),
          '--specpath',str(ROOT/'build')]
    for p in extras:
        args+=['--paths',p]
    for module in ('torch','tensorflow','matplotlib','pandas','IPython','pytest','notebook','tkinter'):
        args+=['--exclude-module',module]
    # 整个 `maps/` 一起打包，**连 index.json 和 evidence/ 也带上**：它们是派生物，
    # 但重建一次要 1~3 分钟，让用户第一次启动就干等是不可接受的（旧版也是把
    # `reference/index` 打进包的）。原图、登记表、特征、软删除状态因此同进同出，
    # 不会出现「有图没特征」或「有特征没登记」这种半截状态。
    #
    # 逐个子项列出来而不是整目录 `maps/`，是为了只排除 `_overview/`：
    # 那三张一图流总览共 137 MB，从不进索引，进包只会让安装包白白大三倍。
    data=[ROOT/'mapmatching/assets',
          *(ROOT/'maps'/name for name in ('hard','nightmare','_unindexed','evidence',
                                          'floors.json','index.json','disabled.json','README.md')),
          ROOT/'scripts/run.cmd',ROOT/'scripts/create_shortcut.ps1',ROOT/'README.md']
    data.extend((ROOT/'mapmatching').glob('*.md'))
    data.extend(ROOT.glob('*.cmd'))
    for path in data:
        if path.exists():
            destination=path.relative_to(ROOT) if path.is_dir() else path.parent.relative_to(ROOT)
            args+=['--add-data',f'{path}{os.pathsep}{destination}']
    args.append(str(ROOT/'mapmatching/launch.py'))
    subprocess.run(args,cwd=ROOT,env=env,check=True)
    from finalize_release import finalize
    finalize()


if __name__=='__main__': main()
