"""Export a USB-debugging-authorized legacy app into the new backup format."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

PACKAGE='com.crypticnotes.mobile'

def preferences(xml):
    result={}
    kinds={'string':'String','boolean':'Boolean','int':'Integer','long':'Long','float':'Float','set':'set'}
    for item in ET.fromstring(xml):
        if item.tag not in kinds:raise ValueError('Unsupported preference type')
        value=(item.text or '') if item.tag=='string' else item.get('value')
        if item.tag=='boolean':
            if value not in ('true','false'):raise ValueError('Invalid boolean')
            value=value=='true'
        elif item.tag in ('int','long'):value=int(value)
        elif item.tag=='float':value=float(value)
        elif item.tag=='set':value=[child.text or '' for child in item]
        result[item.attrib['name']]={'type':kinds[item.tag],'value':value}
    return result

def export(adb,output):
    devices=subprocess.check_output([adb,'devices'],text=True)
    usable=[line.split()[0] for line in devices.splitlines()[1:] if line.endswith('\tdevice')]
    if len(usable)!=1:raise RuntimeError('Connect exactly one phone and authorize USB debugging')
    def read(path,optional=False):
        r=subprocess.run([adb,'-s',usable[0],'exec-out','run-as',PACKAGE,'cat',path],capture_output=True)
        if r.returncode:
            if optional and b'No such file' in r.stderr:return None
            raise RuntimeError('Cannot read legacy app data: '+r.stderr.decode(errors='replace').strip())
        return r.stdout
    # Export only; never force-stop, uninstall or modify either app.
    backup={'format':'crypticnotes-backup','version':1,
            'preferences':preferences(read('shared_prefs/mobile.xml'))}
    saved=read('files/minigame-saves/jellyfish/local-storage.json',optional=True)
    if saved is not None:
        game=json.loads(saved)
        if not isinstance(game,dict) or any(not k.startswith('jellyfish.') or not isinstance(v,str) for k,v in game.items()):
            raise ValueError('Invalid mini-game save')
        backup['game']=game
    if output.exists():raise FileExistsError('Output exists; choose a new backup filename')
    with output.open('x',encoding='utf-8') as f:json.dump(backup,f,ensure_ascii=False,indent=2,allow_nan=False)
    print('Backup saved:',output.resolve())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb',default=shutil.which('adb'))
    parser.add_argument('--output',type=Path,default=Path('legacy-android-backup.json'))
    args=parser.parse_args()
    if not args.adb:parser.error('Install Android platform-tools or pass --adb path/to/adb')
    export(args.adb,args.output)

if __name__=='__main__':main()
