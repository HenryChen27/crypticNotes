"""Mirror a complete verified GitHub snapshot using exact-file temporary upload grants."""
import argparse,concurrent.futures,datetime,json,subprocess,time,sys,hashlib,shutil
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.gitcode_release import GitCode,plan,publish
CHECKOUT=ROOT/'release/gitcode'

def git(*args):
    subprocess.run(['git','-C',str(CHECKOUT),*args],check=True)

def snapshot_plan(local,release):
    required=set(json.loads((CHECKOUT/'scripts/artifacts.json').read_text(encoding='utf-8')))|set(local['files'])
    assets={a['name']:a for a in release['assets']};files={}
    for name in sorted(required):
        a=assets.get(name,{})
        digest=a.get('digest','').removeprefix('sha256:')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or not isinstance(a.get('size'),int):raise RuntimeError('Incomplete GitHub snapshot: '+name)
        entry=dict(size=a['size'],sha256=digest)
        if name in local['files']:
            own=local['files'][name]
            if own['sha256']!=digest or own['size']!=entry['size']:raise RuntimeError('GitHub snapshot differs from local release job: '+name)
            entry['path']=own['path']
        files[name]=entry
    return dict(count=len(files),total_bytes=sum(e['size'] for e in files.values()),files=files)

def refresh_readme(receipt):
    p=CHECKOUT/'README.md';text=p.read_text(encoding='utf-8')
    rows=['## 下载','', '[GitCode 国内下载](https://gitcode.com/weixin_51917701/crypticNotes/releases) · [GitHub 备用下载](https://github.com/HenryChen27/crypticNotes/releases/latest)','',
          '当前发布：'+receipt['tag']+'。以下安装包和地图库均已核对大小及 SHA-256，并通过匿名下载验证。','', '| 平台 / 模块 | 下载 | 大小 |','| --- | --- | --- |']
    names={'IdentityVMapAssistant-Windows-x64.zip':'Windows', 'IdentityVMapAssistant-Android-arm64.apk':'Android ARM64', 'IdentityVMapAssistant-macOS-arm64.zip':'Apple 芯片 Mac','IdentityVMapAssistant-macOS-x64.zip':'Intel Mac','IdentityVMapAssistant-Maps-lianghapi.zip':'凉哈皮地图库','IdentityVMapAssistant-Maps-zhanshi.zip':'展十地图库'}
    for f in receipt['files']:
        if f['name'] in names:rows.append('| '+names[f['name']]+' | ['+f['name']+']('+f['url']+') | '+format(f['size']/1000000,'.1f')+' MB |')
    rows+=['','Source code 不是安装包。完整文件名、大小及 SHA-256 见 [发布清单](published-files.json)。','']
    text=text[:text.index('## 下载')]+'\n'.join(rows)+'\n'+text[text.index('## 使用'):]
    text=text.replace('此阶段 GitCode 提供手动下载入口。插件内更新、模块清单中的下载地址仍使用原 GitHub 通道，尚未切换。','新版客户端的主程序和地图库更新优先使用 GitCode；查询连接失败时回退 GitHub。旧版需要先更新一次或从本页手动安装。小游戏资源仍使用原仓库。')
    p.write_text(text,encoding='utf-8')
    (CHECKOUT/'published-files.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    p=CHECKOUT/'distribution.json';state=json.loads(p.read_text(encoding='utf-8'));state.update(status='available',release_tag=receipt['tag'],verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),client_updates_migrated=True,files_manifest='published-files.json');p.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    git('add','README.md','distribution.json','published-files.json');git('commit','-m','Synchronize verified release '+receipt['tag']);git('push','origin','main')

def mirror(jobs,tag=None,release=None):
    prepared=plan(jobs)
    if release is not None:prepared=snapshot_plan(prepared,release)
    tag=tag or 'v'+datetime.datetime.now().strftime('%Y.%m.%d-%H%M%S')
    manifest={n:{k:e[k] for k in ('size','sha256')} for n,e in prepared['files'].items()}
    (CHECKOUT/'scripts/artifacts.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    git('add','scripts/artifacts.json')
    changed=subprocess.run(['git','-C',str(CHECKOUT),'diff','--cached','--quiet']).returncode
    if changed:git('commit','-m','Prepare verified artifacts '+tag);git('push','origin','main')
    client=GitCode();base=client.repository
    releases=client.api(base+'/releases?per_page=100')
    if not any(r.get('tag_name')==tag for r in releases):
        client.api(base+'/releases',dict(tag_name=tag,name='小布偶插件 · '+tag.removeprefix('v')+'（上传中）',body='上传完成并通过校验后才转为正式版本。',target_commitish='main',release_status='pre'),'POST')
    current=client.api(base+'/releases/tags/'+quote(tag,safe=''));assets={a['name']:a for a in current['assets']}
    missing=[]
    for name,e in prepared['files'].items():
        if name in assets:
            if assets[name].get('digest')!='sha256:'+e['sha256'] or assets[name].get('size')!=e['size']:raise RuntimeError('Existing GitCode file differs: '+name)
        else:missing.append(name)
    if missing:
        def grant(name):return name,client.api(base+'/releases/'+quote(tag,safe='')+'/upload_url?file_name='+quote(name,safe=''))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:grants=dict(pool.map(grant,missing))
        api=GitCode();api.base=api.base.replace('/v5','/v8')
        run=api.api(base+'/actions/workflows/mirror-release.yml/dispatches',dict(ref='main',inputs={'upload_plan':json.dumps(grants)}),'POST')
        run_id=run['workflow_run_id'];print('GitCode transfer run:',run_id,flush=True)
        (ROOT/'out'/('gitcode-cloud-run-'+tag+'.json')).write_text(json.dumps(run),encoding='utf-8')
        for attempt in range(120):
            jobs_state=api.api(base+'/actions/runs/'+run_id+'/jobs').get('jobs',[])
            statuses=[j['status'] for j in jobs_state]
            if any(s in ('FAILED','CANCELED','IGNORED','SUSPEND') for s in statuses):raise RuntimeError('GitCode transfer failed; retry the same tag: '+tag)
            if statuses and all(s=='COMPLETED' for s in statuses):break
            if attempt%3==0:print('GitCode transfer:',','.join(statuses) or 'queued',flush=True)
            time.sleep(15)
        else:raise RuntimeError('GitCode transfer timeout; release remains pre-release')
        current=client.api(base+'/releases/tags/'+quote(tag,safe=''))
        by_name={a['name']:a for a in current['assets']}
        if any(n not in by_name or by_name[n].get('digest')!='sha256:'+e['sha256'] or by_name[n].get('size')!=e['size'] for n,e in prepared['files'].items()):raise RuntimeError('GitCode callback verification failed')
    receipt=publish(jobs,tag,prepared=prepared)
    for name,e in prepared['files'].items():
        if e.get('path'):
            source=Path(e['path'])
            if hashlib.sha256(source.read_bytes()).hexdigest()!=e['sha256']:raise RuntimeError('Local package changed after verification: '+name)
            target=ROOT/'release'/name;temporary=target.with_name(target.name+'.publish-tmp')
            shutil.copy2(source,temporary);temporary.replace(target)
    refresh_readme(receipt)
    return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--jobs',type=Path,nargs='+',required=True);parser.add_argument('--tag');parser.add_argument('--github-snapshot',action='store_true');args=parser.parse_args()
    release=None
    if args.github_snapshot:
        from scripts.release_manager import GitHub
        release=GitHub().api('/releases/latest')
    mirror(args.jobs,args.tag,release)
if __name__=='__main__':main()
