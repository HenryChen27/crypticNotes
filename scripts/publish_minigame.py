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
    if catalog.get('schema')!=1 or catalog.get('id')!='jellyfish':
        raise SystemExit('Invalid game catalog')
    tags=set()
    files={}
    for info in catalog['packages'].values():
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
    try:
        release=github.api('/releases/tags/'+tag)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        release=github.api('/releases',{'tag_name':tag,'name':'合成大水母 · 电脑悬浮版',
            'target_commitish':'main','body':'加页手记可选小游戏包。保留原游戏界面，无需安装 Node.js 或浏览器。'},'POST')
    # Preserve already published architectures when uploading another one later.
    asset=next((a for a in release['assets'] if a['name']=='desktop-games.json'),None)
    if asset:
        previous=json.loads(github.download(asset['browser_download_url']))
        previous['packages'].update(catalog['packages'])
        catalog=previous
        args.catalog.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    files['desktop-games.json']=releases.digest(args.catalog)
    state={'id':'jellyfish-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'),
           'release_id':release['id'],'files':files,'notes':''}
    # This helper publishes to latest; refuse to replace a different release.
    if github.api('/releases/latest')['id']!=release['id']:
        raise SystemExit('The requested game release is not latest; use a new version tag')
    releases.publish(github,state,args.catalog.parent)


if __name__=='__main__':main()
