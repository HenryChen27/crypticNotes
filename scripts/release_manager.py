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

PACKAGES = {
    'android': ['IdentityVMapAssistant-Android-arm64.apk'],
    'windows': ['IdentityVMapAssistant-Windows-x64.zip'],
    'mac': ['IdentityVMapAssistant-macOS-arm64.zip', 'IdentityVMapAssistant-macOS-x64.zip'],
}

def input_fingerprint(platform, root=None):
    """Hash release inputs, not timestamps, build output or automatic versions."""
    root = root or ROOT
    patterns = ['maps/hard/**', 'maps/nightmare/**', 'maps/floors.json',
                'mapmatching/src/**', 'mapmatching/config.py', 'mapmatching/paths.py',
                'mapmatching/__init__.py']
    if platform == 'android':
        patterns += ['android/app/src/**', 'android/*.gradle', 'android/app/*.gradle',
                     'android/gradle.properties', 'scripts/prepare_android.py',
                     'mapmatching/assets/map-ui/**', 'mapmatching/assets/fonts/HYDiWRGJ.ttf']
    else:
        patterns += ['mapmatching/**', 'requirements*.txt', 'scripts/dist_extras.py',
                     'scripts/run.cmd', 'scripts/create_shortcut.ps1', 'maps/disabled.json',
                     'maps/_unindexed/**', 'docs/images/**', 'README.md', '*.cmd', 'maps/README.md']
        patterns += (['scripts/build_windows.py', 'scripts/finalize_release.py',
                      'scripts/update-client.ps1', 'scripts/更新.cmd'] if platform == 'windows' else
                     ['scripts/build_macos.py', 'release/crypticNotes/.github/workflows/macos.yml'])
    files = sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()
                    and not any(part in ('__pycache__', '.pytest_cache', 'tests') for part in p.parts)
                    and p.suffix not in ('.pyc', '.pyo', '.log')})
    hashes = {}
    for path in files:
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if path.suffix in ('.py', '.gradle', '.txt', '.json', '.yml', '.cmd', '.ps1', '.properties'):
            data = data.replace(b'\r\n', b'\n')
        if name == 'android/app/build.gradle':
            data = re.sub(rb'versionCode\s+\d+', b'versionCode AUTO', data)
            data = re.sub(rb"versionName\s+'[^']+'", b"versionName 'AUTO'", data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    return {'schema': 1, 'sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}

def unchanged(current, baseline, assets):
    return (baseline.get('input') == current and bool(baseline.get('packages'))
            and all(assets.get(n) == sha for n, sha in baseline['packages'].items()))

def interactive(args):
    while True:
        print('\n1 选择平台打包   2 选择平台打包并发布   3 上传已有包 / 重试发布   0 退出')
        action = input('请输入编号：').strip()
        if action == '0': return False
        if action == '3':
            jobs = sorted((ROOT/'release/jobs').glob('*/release-job.json'), reverse=True)
            jobs = [p for p in jobs if json.loads(p.read_text(encoding='utf-8')).get('ready')]
            for i, p in enumerate(jobs, 1): print(i, p.parent.name)
            choice = input('选择批次编号（直接回车返回）：').strip()
            if choice.isdigit() and 1 <= int(choice) <= len(jobs):
                args.resume = jobs[int(choice)-1]; return True
            continue
        if action not in ('1', '2'): continue
        print('1 Windows   2 Android   3 Mac（两个架构）   4 全部')
        selected = input('选择平台，可用空格分隔：').split()
        lookup = {'1':'windows', '2':'android', '3':'mac', '4':'all'}
        if not selected or any(n not in lookup for n in selected):
            print('编号无效，请重新选择。'); continue
        args.platforms = [lookup[n] for n in selected]
        args.publish = action == '2'
        if args.publish:
            notes = input('更新公告文件路径（可留空）：').strip().strip('"')
            if notes: args.notes = Path(notes)
        return True

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
    if not args.platforms and not args.resume:
        if not interactive(args): return
    if args.resume:
        state=json.loads(args.resume.read_text(encoding='utf-8'))
        if not state.get('ready'):raise RuntimeError('Job is not fully built; start a new build')
        publish(GitHub(),state,args.resume.resolve().parent);return
    platforms=set(args.platforms)
    if 'all' in platforms:platforms={'windows','android','mac'}
    if not platforms:raise RuntimeError('No platform selected')
    github=GitHub() if args.publish or 'mac' in platforms else None
    release = github.api('/releases/latest') if github else None
    inputs = {p: input_fingerprint(p) for p in platforms}
    for platform in sorted(platforms.copy()):
        baseline = {}
        assets = {}
        if args.publish:
            baseline = github.manifest(release, platform+'-inputs.json')
            assets = {a['name']: a.get('digest', '').removeprefix('sha256:') for a in release['assets']}
        else:
            for job in sorted((ROOT/'release/jobs').glob('*/release-job.json'), reverse=True):
                previous = json.loads(job.read_text(encoding='utf-8'))
                if not previous.get('ready'): continue
                sidecar = job.parent/(platform+'-inputs.json')
                if not sidecar.exists(): continue
                candidate = json.loads(sidecar.read_text(encoding='utf-8'))
                if candidate.get('input') != inputs[platform]: continue
                baseline = candidate
                assets = {n: digest(job.parent/n) for n in candidate.get('packages', {}) if (job.parent/n).is_file()}
                break
        if unchanged(inputs[platform], baseline, assets):
            print(platform, '内容没有变化，跳过升版本、打包和发布。')
            platforms.remove(platform)
        elif not baseline:
            print(platform, '没有可验证的历史内容记录；本次构建成功后建立记录，之后自动跳过未改动的平台。')
    if not platforms:
        print('所选平台均无变化，没有执行后续操作。'); return
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    directory=ROOT/'release/jobs'/stamp;directory.mkdir(parents=True)
    state={'id':stamp,'platforms':sorted(platforms),'ready':False,'files':{},
        'notes':args.notes.read_text(encoding='utf-8') if args.notes else f'### {stamp} 更新\n平台：'+', '.join(sorted(platforms))}
    if github:state['release_id']=release['id']
    if 'android' in platforms:
        old=github.manifest(github.api('/releases/latest'),'android-update.json') if github else {}
        p=ROOT/'android/app/build.gradle'
        shutil.copy2(p,directory/'build.gradle.before')
        text,code,android_version=bump_android(p.read_text(encoding='utf-8'),old.get('versionCode',0),old.get('versionName','0.0.0'))
        p.write_text(text,encoding='utf-8');print('Android:',android_version,code)
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
        manifest=dict(packageName='com.crypticnotes.mobile',versionCode=code,versionName=android_version,
            asset=n,size=apk.stat().st_size,sha256=digest(apk))
        (directory/'android-update.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        wanted.update([n,'android-update.json'])
    if 'mac' in platforms:wanted.update(mac_build(github,branch,sha,directory))
    for platform in platforms:
        if input_fingerprint(platform) != inputs[platform]:
            raise RuntimeError('构建期间输入文件发生变化，停止发布：'+platform)
        sidecar = platform+'-inputs.json'
        (directory/sidecar).write_text(json.dumps({
            'input': inputs[platform],
        'packages': {n: digest(directory/n) for n in (
            PACKAGES[platform] + (['android-update.json'] if platform == 'android' else
            ['windows-update.json', 'update-client.ps1'] if platform == 'windows' else []))},
        }, indent=2), encoding='utf-8')
        wanted.add(sidecar)
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
