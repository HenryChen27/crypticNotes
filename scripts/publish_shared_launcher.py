"""Publish only common launcher assets; never replace upstream game resources."""
import argparse,json,time,io,zipfile
from pathlib import Path
import release_manager as r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=int);parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    github=r.GitHub();out=r.ROOT/'out/shared-launcher-release';out.mkdir(parents=True,exist_ok=True)
    run=args.run
    if not run:
        branch,sha=r.sync_sources(github)
        path='/actions/workflows/native-games.yml'
        before={x['id'] for x in github.api(path+'/runs?per_page=20')['workflow_runs']}
        github.api(path+'/dispatches',{'ref':branch},'POST')
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            selected=next((x for x in github.api(path+'/runs?per_page=20')['workflow_runs'] if x['id'] not in before and x['head_sha']==sha),None)
            if selected:run=selected['id'];break
            time.sleep(5)
        if not run:raise RuntimeError('Launcher workflow dispatch not found')
        (out/'run.json').write_text(json.dumps({'run':run,'source_commit':sha}))
    last=None;deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        info=github.api('/actions/runs/'+str(run))
        if info['status']!=last:print('Launcher workflow:',info['html_url'],info['status'],flush=True);last=info['status']
        if info['status']=='completed':
            if info['conclusion']!='success':raise RuntimeError('Launcher workflow failed: '+info['html_url'])
            break
        time.sleep(15)
    else:raise RuntimeError('Launcher workflow timeout')
    local=r.ROOT/'out/minigames-native';catalog=json.loads((local/'native-desktop-games.json').read_text(encoding='utf-8'))
    launchers={'windows-x64':catalog['launchers']['windows-x64']}
    import shutil
    shutil.copy2(local/'GameLauncher-windows-x64.zip',out/'GameLauncher-windows-x64.zip')
    for artifact in github.api('/actions/runs/'+str(run)+'/artifacts')['artifacts']:
        with zipfile.ZipFile(io.BytesIO(github.download(artifact['archive_download_url']))) as z:
            for name in z.namelist():
                if name.startswith('GameLauncher-') and name.endswith('.zip'):(out/name).write_bytes(z.read(name))
                elif name=='native-desktop-games.json':
                    for key,value in json.loads(z.read(name))['launchers'].items():
                        if key.startswith('macos-'):launchers[key]=value
    if set(launchers)!={'windows-x64','macos-arm64','macos-x64'}:raise RuntimeError('Missing platform launcher')
    r.REPO='HenryChen27/mini_games';release=github.api('/releases/latest');current=github.manifest(release,'native-desktop-games.json')
    files={}
    for platform,entry in launchers.items():
        name='GameLauncher-'+platform+'.zip';p=out/name
        if r.digest(p)!=entry['sha256'] or p.stat().st_size!=entry['size']:raise RuntimeError('Launcher checksum mismatch: '+name)
        entry['url']='https://github.com/'+r.REPO+'/releases/download/'+release['tag_name']+'/'+name
        current['launchers'][platform]=entry;files[name]=r.digest(p)
    (out/'native-desktop-games.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    files['native-desktop-games.json']=r.digest(out/'native-desktop-games.json')
    # Upstream collection/game archives and their version identities remain unchanged.
    state={'id':'shared-launcher-'+str(run),'ready':True,'release_id':release['id'],'files':files,'notes':''}
    (out/'release-job.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print('Verified common launchers:',out,flush=True)
    if args.publish:r.publish(github,state,out)
if __name__=='__main__':main()
