"""GitCode distribution setup/status and verified local upload plans. No GitHub writes."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,urllib.request,urllib.error,http.client,time
from urllib.parse import quote,urlsplit
CONFIG=Path(__file__).with_suffix('.json')
class SameHost(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        from urllib.parse import urlsplit
        if urlsplit(url).scheme!='https' or urlsplit(url).hostname!='api.gitcode.com':
            raise RuntimeError('GitCode API redirected outside its trusted host')
        return super().redirect_request(req,fp,code,msg,headers,url)
class GitCode:
    def __init__(self,config=None):
        self.config=config or json.loads(CONFIG.read_text(encoding='utf-8'))
        token=os.environ.get('GITCODE_TOKEN')
        if not token:
            env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'Never'}
            result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=gitcode.com\nusername='+self.config['owner']+'\n\n',text=True,capture_output=True,env=env)
            if result.returncode==0:token=dict(x.split('=',1) for x in result.stdout.splitlines() if '=' in x).get('password')
        if not token:raise RuntimeError('GitCode credential missing: set GITCODE_TOKEN or configure the OS Git credential manager')
        self._headers={'PRIVATE-TOKEN':token,'User-Agent':'crypticNotes-publisher','Accept':'application/json'}
        self.base=self.config['api_base']
        self.repository='/repos/'+self.config['owner']+'/'+self.config['repo']
        self.opener=urllib.request.build_opener(SameHost())
    def api(self,path,data=None,method=None):
        headers=dict(self._headers)
        if data is not None:headers["Content-Type"]="application/json"
        req=urllib.request.Request(self.base+path,headers=headers,data=json.dumps(data).encode() if data is not None else None,method=method)
        try:
            with self.opener.open(req,timeout=45) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('GitCode API HTTP '+str(error.code)) from None
    def status(self):
        user=self.api('/user');repo=self.api(self.repository)
        branches=self.api(self.repository+'/branches?per_page=100')
        releases=self.api(self.repository+'/releases?per_page=100')
        return dict(account=user.get('login'),repository=repo.get('full_name'),private=repo.get('private'),default_branch=repo.get('default_branch'),branches=[r['name'] for r in branches],releases=[r.get('tag_name') for r in releases],client_updates_enabled=self.config['client_updates_enabled'])
def plan(jobs):
    files={}
    for job in jobs:
        state=json.loads(job.read_text(encoding='utf-8'))
        if not state.get('ready'):raise RuntimeError('Release job is not ready')
        for name,expected in state['files'].items():
            if Path(name).name!=name or '/' in name or '\\' in name:raise RuntimeError('Invalid artifact name')
            path=job.parent/name
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual!=expected:raise RuntimeError('Artifact checksum mismatch: '+name)
            if name in files and files[name]['sha256']!=expected:raise RuntimeError('Conflicting artifacts: '+name)
            files[name]=dict(path=str(path.resolve()),size=path.stat().st_size,sha256=actual)
    return dict(mode='plan-only',count=len(files),total_bytes=sum(x['size'] for x in files.values()),files=files)
def anonymous_digest(url):
    if urlsplit(url).scheme!='https':raise RuntimeError('Download must use HTTPS')
    digest=hashlib.sha256();size=0
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'crypticNotes-download-check','Cache-Control':'no-cache','Accept-Encoding':'identity'}),timeout=180) as response:
            while chunk:=response.read(1024*1024):digest.update(chunk);size+=len(chunk)
    except Exception:raise RuntimeError('Anonymous download verification failed') from None
    return digest.hexdigest(),size

def publish(jobs,tag,prepared=None):
    prepared=prepared or plan(jobs);client=GitCode();base=client.repository
    releases=client.api(base+'/releases?per_page=100')
    release=next((r for r in releases if r.get('tag_name')==tag),None)
    title='小布偶插件 · '+tag.removeprefix('v')
    body='Windows、Android、macOS 安装包及凉哈皮、展十地图库。\n\n新版客户端主程序与地图库更新优先使用 GitCode；查询连接失败时回退 GitHub。旧用户需先安装一次过渡更新。小游戏资源暂用原仓库。'
    if release is None:
        release=client.api(base+'/releases',dict(tag_name=tag,name=title+'（上传中）',body=body,target_commitish='main',release_status='pre'),'POST')
        print('Created GitCode release:',tag,flush=True)
    quoted=quote(tag,safe='')
    verified=[]
    for name,entry in prepared['files'].items():
        release=client.api(base+'/releases/tags/'+quoted+'?v='+str(time.time_ns()))
        existing=next((a for a in release.get('assets',[]) if a.get('name')==name),None)
        if existing:
            if existing.get('digest','').removeprefix('sha256:') not in ('',entry['sha256']):raise RuntimeError('Existing GitCode attachment differs: '+name)
        else:
            if not entry.get('path'):raise RuntimeError('Cloud attachment missing: '+name)
            upload=client.api(base+'/releases/'+quoted+'/upload_url?file_name='+quote(name,safe=''))
            url=urlsplit(upload['url'])
            if url.scheme!='https':raise RuntimeError('Upload must use HTTPS')
            headers=dict(upload['headers']);headers['Content-Length']=str(entry['size'])
            if any(k.lower() in ('private-token','authorization') for k in headers):raise RuntimeError('Unexpected credential header on storage upload')
            connection=http.client.HTTPSConnection(url.hostname,url.port,timeout=120,blocksize=1024*1024)
            try:
                print('Uploading GitCode:',name,entry['size'],'bytes',flush=True)
                with Path(entry['path']).open('rb') as source:
                    class Progress:
                        sent=0
                        reported=0
                        def read(self,size):
                            data=source.read(size);self.sent+=len(data)
                            if self.sent-self.reported>=4*1024*1024 or (not data and self.sent):
                                print('Upload bytes:',name,self.sent,flush=True);self.reported=self.sent
                            return data
                    stream=Progress()
                    connection.request('PUT',url.path+('?' +url.query if url.query else ''),body=stream,headers=headers)
                    response=connection.getresponse();response.read()
                    if not 200<=response.status<300:raise RuntimeError('GitCode storage upload HTTP '+str(response.status)+': '+name)
            finally:connection.close()
            for attempt in range(20):
                release=client.api(base+'/releases/tags/'+quoted+'?v='+str(time.time_ns()))
                existing=next((a for a in release.get('assets',[]) if a.get('name')==name),None)
                if existing:break
                time.sleep(2)
            if not existing:raise RuntimeError('Attachment callback not registered: '+name)
        for attempt in range(3):
            try:
                digest,size=anonymous_digest(existing['browser_download_url'])
                if digest==entry['sha256'] and size==entry['size']:break
            except RuntimeError:
                if attempt==2:raise
            if attempt==2:raise RuntimeError('Remote attachment verification failed: '+name)
            print('Retrying anonymous verification:',name,flush=True)
        verified.append(dict(name=name,sha256=digest,size=size,url=existing['browser_download_url']))
        print('Verified GitCode upload/download:',name,flush=True)
    # Additional full manifest covers both Mac architectures and both libraries.
    client.api(base+'/releases/'+quoted,dict(name=title,body=body,release_status='latest'),'PATCH')
    result=dict(repository=client.config['repository_url'],tag=tag,files=verified)
    destination=Path('out')/('gitcode-published-'+tag+'.json');destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Published GitCode:',tag,flush=True)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','plan','publish'])
    parser.add_argument('--jobs',type=Path,nargs='+')
    parser.add_argument('--tag',default='v2026.10.30')
    args=parser.parse_args()
    if args.action in ('plan','publish') and not args.jobs:parser.error('plan/publish requires --jobs')
    result=GitCode().status() if args.action=='status' else publish(args.jobs,args.tag) if args.action=='publish' else plan(args.jobs)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as error:raise SystemExit(str(error))
