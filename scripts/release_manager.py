"""Selective desktop/Android release manager. Run from the development workspace."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from urllib.parse import urlsplit, quote

ROOT = Path(__file__).resolve().parents[1]
REPO = 'HenryChen27/crypticNotes'
CERT = 'b7b3d8249c3d02aeae26f3bac11e966bd0addb073639933037b1a282c2699fb2'

def run(args, cwd=ROOT, env=None, capture=False):
    print('>', ' '.join(map(str,args)), flush=True)
    return subprocess.run(list(map(str,args)), cwd=cwd, env=env, check=True,
        stdout=subprocess.PIPE if capture else None, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0).stdout

def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def bump_android(text, remote_code=0, remote_name='0.0.0'):
    code=max(int(re.search(r'versionCode\s+(\d+)',text)[1]),remote_code)+1
    name=re.search(r"versionName\s+'([^']+)'",text)[1]
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(.*)',name)
    if not match: raise ValueError('Android versionName must have major.minor.patch format')
    local=tuple(map(int,match.groups()[:3]))
    other=re.match(r'(\d+)\.(\d+)\.(\d+)',remote_name)
    base=max(local,tuple(map(int,other.groups())) if other else local)
    name=f'{base[0]}.{base[1]}.{base[2]+1}{match[4]}'
    text=re.sub(r'versionCode\s+\d+',f'versionCode {code}',text,count=1)
    return re.sub(r"versionName\s+'[^']+'",f"versionName '{name}'",text,count=1),code,name

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result and urlsplit(req.full_url).hostname!=urlsplit(newurl).hostname:
            result.remove_header('Authorization')
        return result

class GitHub:
    def __init__(self):
        token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not token:
            result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
                capture_output=True,text=True,check=True)
            token=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line).get('password')
        if not token: raise RuntimeError('Log into GitHub with Git Credential Manager or set GH_TOKEN')
        self.headers={'Authorization':'Bearer '+token,'User-Agent':'crypticNotes-release','Accept':'application/vnd.github+json'}
    def api(self,path,data=None,method=None):
        req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,headers=self.headers,
            data=json.dumps(data).encode() if data is not None else None,method=method)
        with urllib.request.urlopen(req,timeout=120) as r:
            b=r.read();return json.loads(b) if b else None
    def download(self,url):
        with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url,headers=self.headers),timeout=600) as r:
            return r.read()
    def manifest(self,release,name):
        asset=next((a for a in release['assets'] if a['name']==name),None)
        return json.loads(self.download(asset['browser_download_url']+'?v='+str(time.time_ns()))) if asset else {}

def sync_sources(github):
    checkout=ROOT/'release/crypticNotes'
    if not (checkout/'.git').exists():
        raise RuntimeError('Missing release/crypticNotes checkout; see docs/releasing.md')
    if run(['git','status','--porcelain'],checkout,capture=True).strip():
        raise RuntimeError('Public checkout has uncommitted changes; review them first')
    branch=github.api('')['default_branch']
    run(['git','fetch','origin',branch],checkout)
    # Refuse divergence; never overwrite somebody else's remote commits.
    run(['git','merge','--ff-only','origin/'+branch],checkout)
    names=run(['git','ls-files','-z'],ROOT,capture=True).split('\0')
    files=[n for n in names if n and (n.startswith(('mapmatching/','android/','maps/','scripts/','docs/'))
        or n in ('README.md','requirements.txt','requirements-build.txt'))]
    for name in files:
        source=ROOT/name
        if not source.is_file(): raise RuntimeError('Tracked source missing: '+name)
        target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    # Include this entry point even before it has been committed locally.
    extra=['scripts/release_manager.py','scripts/release-menu.cmd','docs/releasing.md']
    if (ROOT/'macos-version.json').exists():extra.append('macos-version.json')
    for name in extra:
        target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    run(['git','add','mapmatching','android','maps','scripts','docs','README.md'],checkout)
    if (checkout/'macos-version.json').exists():run(['git','add','macos-version.json'],checkout)
    if run(['git','diff','--cached','--name-only'],checkout,capture=True).strip():
        run(['git','commit','-m','Release: synchronize reviewed source and map library'],checkout)
    run(['git','push','origin','HEAD:'+branch],checkout)
    return branch,run(['git','rev-parse','HEAD'],checkout,capture=True).strip()

def mac_build(github,branch,sha,directory):
    path='/actions/workflows/macos.yml'
    before={r['id'] for r in github.api(path+'/runs?per_page=30')['workflow_runs']}
    github.api(path+'/dispatches',{'ref':branch},'POST')
    deadline=time.monotonic()+3600;selected=None
    while time.monotonic()<deadline:
        if selected is None:
            selected=next((r['id'] for r in github.api(path+'/runs?per_page=30')['workflow_runs']
                if r['id'] not in before and r['head_sha']==sha and r['event']=='workflow_dispatch'),None)
        if selected:
            result=github.api('/actions/runs/'+str(selected))
            print('Mac:',result['html_url'],result['status'],flush=True)
            if result['status']=='completed':
                if result['conclusion']!='success': raise RuntimeError('Mac workflow failed: '+result['html_url'])
                break
        time.sleep(15)
    else: raise RuntimeError('Mac workflow timed out; inspect GitHub Actions before retrying')
    wanted={f'IdentityVMapAssistant-macOS-{a}.zip' for a in ('arm64','x64')}|{f'macos-{a}-SHA256SUMS.txt' for a in ('arm64','x64')}
    found=set()
    for artifact in github.api(f'/actions/runs/{selected}/artifacts')['artifacts']:
        with zipfile.ZipFile(io.BytesIO(github.download(artifact['archive_download_url']))) as z:
            for name in z.namelist():
                if name in wanted:
                    (directory/name).write_bytes(z.read(name));found.add(name)
    if found!=wanted: raise RuntimeError('Missing Mac release artifacts')
    for a in ('arm64','x64'):
        if digest(directory/f'IdentityVMapAssistant-macOS-{a}.zip')!=(directory/f'macos-{a}-SHA256SUMS.txt').read_text().split()[0]:
            raise RuntimeError('Mac checksum mismatch')
    return wanted

def publish(github,state,directory):
    release=github.api('/releases/latest')
    if state.get('release_id') and state['release_id']!=release['id']:
        raise RuntimeError('Latest release changed since build; review before publishing')
    # A newer concurrent release must not be downgraded by an old resume.
    for name,key in (('android-update.json','versionCode'),('windows-update.json','build')):
        if name in state['files']:
            old=github.manifest(release,name);new=json.loads((directory/name).read_text())
            if old.get(key,0)>=new[key] and old!=new:raise RuntimeError('A newer version is already published: '+name)
    staged=[]
    for name,expected in state['files'].items():
        path=directory/name
        if digest(path)!=expected:raise RuntimeError('Artifact changed: '+name)
        temp=name+'.pending-'+expected[:12]
        assets=github.api('/releases/'+str(release['id']))['assets']
        live=next((a for a in assets if a['name']==name and a.get('digest')=='sha256:'+expected),None)
        if live:continue
        result=next((a for a in assets if a['name']==temp),None)
        if not result:
            url=urlsplit(release['upload_url'].split('{')[0]+'?name='+quote(temp))
            conn=http.client.HTTPSConnection(url.hostname,timeout=900)
            with path.open('rb') as stream:
                conn.request('POST',url.path+'?'+url.query,body=stream,headers={**github.headers,
                    'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size)})
                response=conn.getresponse();result=json.loads(response.read())
            conn.close()
            if response.status!=201:raise RuntimeError('Upload failed: '+name)
        if result.get('digest')!='sha256:'+expected:raise RuntimeError('Remote checksum mismatch: '+name)
        staged.append((name,result['id']))
        print('Verified upload:',name,flush=True)
    # All uploads complete before replacing anything. Manifests are switched last.
    for name,ident in sorted(staged,key=lambda x:x[0].endswith('-update.json')):
        for old in github.api('/releases/'+str(release['id']))['assets']:
            if old['name']==name:github.api('/releases/assets/'+str(old['id']),method='DELETE')
        github.api('/releases/assets/'+str(ident),{'name':name},'PATCH')
    if state.get('notes'):
        marker='<!-- release-job:'+state['id']+' -->'
        body=github.api('/releases/'+str(release['id'])).get('body') or ''
        if marker not in body:
            github.api('/releases/'+str(release['id']),{'body':marker+'\n'+state['notes']+'\n\n---\n'+body},'PATCH')
    final=github.api('/releases/'+str(release['id']))
    for name,expected in state['files'].items():
        if not any(a['name']==name and a.get('digest')=='sha256:'+expected for a in final['assets']):
            raise RuntimeError('Published verification failed: '+name)
    print('Published:',final['html_url'],flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platforms',nargs='+',choices=['windows','android','mac','all'])
    parser.add_argument('--publish',action='store_true',help='Upload selected packages to existing latest Release')
    parser.add_argument('--notes',type=Path,help='UTF-8 release announcement; prepended without deleting other platform notes')
    parser.add_argument('--resume',type=Path,help='Retry publication from a completed release-job.json; no rebuild or version bump')
    args=parser.parse_args()
    if args.resume:
        state=json.loads(args.resume.read_text(encoding='utf-8'))
        if not state.get('ready'):raise RuntimeError('Job is not fully built; start a new build')
        publish(GitHub(),state,args.resume.resolve().parent);return
    if not args.platforms:
        print('1 Windows  2 Android  3 Mac (both architectures)  4 All')
        selected=input('Choose numbers separated by spaces: ').split()
        lookup={'1':'windows','2':'android','3':'mac','4':'all'}
        args.platforms=[lookup[n] for n in selected]
        args.publish=input('Publish after building? [y/N]: ').lower()=='y'
    platforms=set(args.platforms)
    if 'all' in platforms:platforms={'windows','android','mac'}
    if not platforms:raise RuntimeError('No platform selected')
    github=GitHub() if args.publish or 'mac' in platforms else None
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/'release/jobs'/stamp;directory.mkdir(parents=True)
    state={'id':stamp,'platforms':sorted(platforms),'ready':False,'files':{},
        'notes':args.notes.read_text(encoding='utf-8') if args.notes else f'### {stamp} 更新\n平台：'+', '.join(sorted(platforms))}
    if github:state['release_id']=github.api('/releases/latest')['id']
    if 'android' in platforms:
        old=github.manifest(github.api('/releases/latest'),'android-update.json') if github else {}
        p=ROOT/'android/app/build.gradle'
        shutil.copy2(p,directory/'build.gradle.before')
        text,code,version=bump_android(p.read_text(encoding='utf-8'),old.get('versionCode',0),old.get('versionName','0.0.0'))
        p.write_text(text,encoding='utf-8');print('Android:',version,code)
    if 'mac' in platforms:
        p=ROOT/'macos-version.json'
        previous=json.loads(p.read_text()) if p.exists() else {'version':'1.0.0','build':0}
        parts=list(map(int,previous['version'].split('.')));parts[-1]+=1
        version={'version':'.'.join(map(str,parts)),'build':previous['build']+1}
        p.write_text(json.dumps(version,indent=2),encoding='utf-8');state['macos_version']=version
    if github:branch,sha=sync_sources(github);state['source_commit']=sha
    wanted=set()
    if 'windows' in platforms:
        run([sys.executable,'scripts/build_windows.py'])
        report=directory/'windows-smoke.json'
        run([ROOT/'dist/IdentityVMapAssistant/IdentityVMapAssistant.exe','--self-test',report])
        if not json.loads(report.read_text(encoding='utf-8')).get('ok'):raise RuntimeError('Windows smoke failed')
        wanted.update(['IdentityVMapAssistant-Windows-x64.zip','windows-update.json','SHA256SUMS.txt'])
        shutil.copy2(ROOT/'scripts/update-client.ps1',directory/'update-client.ps1')
        for n in wanted:shutil.copy2(ROOT/'release'/n,directory/n)
        wanted.add('update-client.ps1')
    if 'android' in platforms:
        run([sys.executable,'scripts/prepare_android.py'])
        env=os.environ.copy()
        env.setdefault('JAVA_HOME',str(ROOT/'out/android-tools/jdk/jdk-17.0.20.1+1'))
        env['ANDROID_USER_HOME']=str(ROOT/'out/android-user');env['GRADLE_USER_HOME']=str(ROOT/'out/android-gradle-cache')
        gradle=ROOT/'out/android-tools/gradle/gradle-8.13/bin/gradle.bat'
        run([gradle,'-p','android','assembleDebug','--console=plain','--no-problems-report'],env=env)
        apk=ROOT/'android/app/build/outputs/apk/debug/app-debug.apk'
        cert=run([Path(env['JAVA_HOME'])/'bin/java.exe','-jar',ROOT/'out/android-tools/sdk/build-tools/35.0.0/lib/apksigner.jar',
            'verify','--print-certs',apk],env=env,capture=True)
        if CERT not in cert:raise RuntimeError('Android signing certificate changed; refuse incompatible update')
        n='IdentityVMapAssistant-Android-arm64.apk';shutil.copy2(apk,directory/n)
        manifest=dict(packageName='com.crypticnotes.mobile',versionCode=code,versionName=version,
            asset=n,size=apk.stat().st_size,sha256=digest(apk))
        (directory/'android-update.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        wanted.update([n,'android-update.json'])
    if 'mac' in platforms:wanted.update(mac_build(github,branch,sha,directory))
    state.update(ready=True,files={n:digest(directory/n) for n in sorted(wanted)})
    job=directory/'release-job.json';job.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Verified build artifacts:',directory,flush=True)
    print('Publication retry: python scripts/release_manager.py --resume',job,flush=True)
    if args.publish:publish(github,state,directory)

if __name__=='__main__':
    lock=ROOT/'out/release-manager.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    owned=False
    try:
        if '--help' not in sys.argv:
            with lock.open('x') as f:f.write(str(os.getpid()))
            owned=True
        main()
    except Exception as error:
        print('FAILED:',str(error),file=sys.stderr);sys.exit(1)
    finally:
        if owned:lock.unlink(missing_ok=True)
