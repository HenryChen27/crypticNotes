"""Compile only the local Windows launcher, without ZIPs or publication."""
from pathlib import Path
import os,shutil,subprocess
root=Path(__file__).resolve().parents[1]
output=root/'build/local-scene-test';output.mkdir(parents=True,exist_ok=True)
runtime=root/'minigames/runtime'
compiler=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
args=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
      '/out:'+str(output/'GameLauncher.exe'),'/win32icon:'+str(root/'build/native-games/GameLauncher.ico'),
      '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll',
      '/r:'+str(runtime/'Microsoft.Web.WebView2.Core.dll'),'/r:'+str(runtime/'Microsoft.Web.WebView2.WinForms.dll'),
      str(root/'scripts/game_launcher/windows.cs')]
subprocess.run(args,check=True)
for path in runtime.iterdir():
    if path.is_file() and (path.suffix=='.dll' or path.name=='safe-exit.js'):shutil.copy2(path,output/path.name)
print('Compiled local launcher only:',output/'GameLauncher.exe')
