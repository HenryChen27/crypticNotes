"""Publish built optional game packages independently of the map plugin."""
import argparse
import datetime
import json
import urllib.error
from pathlib import Path
import release_manager as releases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--catalog',type=Path,default=releases.ROOT/'out/minigames/desktop-games.json')
    parser.add_argument('--publish',action='store_true',help='Upload the verified game ZIPs and download catalog')
    args=parser.parse_args()
    catalog=json.loads(args.catalog.read_text(encoding='utf-8'))
    native=catalog.get('schema')==2
    if catalog.get('schema') not in (1,2) or catalog.get('id')!='jellyfish':
        raise SystemExit('Invalid game catalog')
    tags=set()
    files={}
    entries=[catalog['game'],*catalog['launchers'].values()] if native else catalog['packages'].values()
    for info in entries:
        url=info['url']
        prefix='https://github.com/HenryChen27/Jellyfish/releases/download/'
        if not url.startswith(prefix):raise SystemExit('Invalid download URL')
        tag,name=url[len(prefix):].split('/',1)
        tags.add(tag)
        if '/' in name or '\\' in name:raise SystemExit('Invalid asset filename')
        bundle=args.catalog.parent/name
        if bundle.stat().st_size!=info['size'] or releases.digest(bundle)!=info['sha256']:
            raise SystemExit('Game package changed: '+name)
        files[name]=info['sha256']
    if len(tags)!=1:raise SystemExit('Build all packages under the same release tag')
    tag=tags.pop()
    print('Verified optional packages:',', '.join(files),flush=True)
    if not args.publish:
        print('Not uploaded. Add --publish after reviewing the game packages.')
        return
    releases.REPO='HenryChen27/Jellyfish'
    github=releases.GitHub()
    previous_release=github.api('/releases/latest')
    try:
        release=github.api('/releases/tags/'+tag)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        release=github.api('/releases',{'tag_name':tag,'name':'合成大水母 · 电脑悬浮版',
            'target_commitish':'main','body':'加页手记可选小游戏包。保留原游戏界面，无需安装 Node.js 或浏览器。'},'POST')
    # Preserve already published architectures when uploading another one later.
    catalog_name='native-desktop-games.json' if native else 'desktop-games.json'
    asset=next((a for a in release['assets'] if a['name']==catalog_name),None)
    if asset:
        previous=json.loads(github.download(asset['browser_download_url']))
        if native:
            previous['launchers'].update(catalog['launchers'])
            previous['game']=catalog['game']
        else:
            previous['packages'].update(catalog['packages'])
        catalog=previous
        args.catalog.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    if native:
        # Older Qt prototype clients keep their own schema-1 download catalog.
        legacy=next((a for a in previous_release['assets'] if a['name']=='desktop-games.json'),None)
        if legacy:
            path=args.catalog.parent/'desktop-games.json'
            # The native build source catalog can have this name too; use another
            # local filename above before restoring the legacy public catalog.
            native_path=args.catalog.parent/catalog_name
            native_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
            path.write_bytes(github.download(legacy['browser_download_url']))
            files['desktop-games.json']=releases.digest(path)
            files[catalog_name]=releases.digest(native_path)
        else:
            (args.catalog.parent/catalog_name).write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
            files[catalog_name]=releases.digest(args.catalog.parent/catalog_name)
    else:
        files[catalog_name]=releases.digest(args.catalog)
    state={'id':'jellyfish-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'),
           'release_id':release['id'],'files':files,'notes':''}
    # This helper publishes to latest; refuse to replace a different release.
    if github.api('/releases/latest')['id']!=release['id']:
        raise SystemExit('The requested game release is not latest; use a new version tag')
    releases.publish(github,state,args.catalog.parent)


if __name__=='__main__':main()
