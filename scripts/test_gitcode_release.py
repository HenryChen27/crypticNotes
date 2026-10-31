import hashlib,json,tempfile,unittest
from pathlib import Path
from urllib.request import Request
from scripts.gitcode_release import plan,SameHost
class GitCodeSetupTests(unittest.TestCase):
    def job(self,folder,data=b'package'):
        folder.mkdir();(folder/'app.zip').write_bytes(data)
        p=folder/'release-job.json';p.write_text(json.dumps({'ready':True,'files':{'app.zip':hashlib.sha256(data).hexdigest()}}));return p
    def test_existing_packages_are_planned_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.job(Path(d)/'a');r=plan([p]);self.assertEqual(r['count'],1);self.assertEqual(r['mode'],'plan-only');self.assertEqual((p.parent/'app.zip').read_bytes(),b'package')
    def test_modified_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.job(Path(d)/'a');(p.parent/'app.zip').write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError,'checksum'):plan([p])
    def test_conflicting_jobs_cannot_be_combined(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.job(Path(d)/'a');b=self.job(Path(d)/'b',b'different')
            with self.assertRaisesRegex(RuntimeError,'Conflicting'):plan([a,b])
    def test_api_credentials_cannot_follow_cross_host_redirect(self):
        req=Request('https://api.gitcode.com/api/v5/user',headers={'PRIVATE-TOKEN':'test-value'})
        with self.assertRaisesRegex(RuntimeError,'trusted host'):SameHost().redirect_request(req,None,302,'',{},'https://example.com/')
    def test_snapshot_keeps_unselected_platforms_and_rejects_changed_selected_file(self):
        from unittest.mock import patch
        from scripts import gitcode_cloud_release as cloud
        with tempfile.TemporaryDirectory() as d:
            checkout=Path(d);(checkout/'scripts').mkdir()
            (checkout/'scripts/artifacts.json').write_text(json.dumps({'windows.zip':{},'android.apk':{}}))
            local={'files':{'android.apk':dict(size=7,sha256='a'*64,path='local.apk')}}
            release={'assets':[dict(name='android.apk',size=7,digest='sha256:'+'a'*64),dict(name='windows.zip',size=9,digest='sha256:'+'b'*64)]}
            with patch.object(cloud,'CHECKOUT',checkout):
                result=cloud.snapshot_plan(local,release)
                self.assertEqual(set(result['files']),{'android.apk','windows.zip'})
                self.assertEqual(result['files']['windows.zip']['sha256'],'b'*64)
                local['files']['android.apk']['sha256']='c'*64
                with self.assertRaisesRegex(RuntimeError,'differs'):cloud.snapshot_plan(local,release)

    def test_only_matching_checkpoints_skip_downloads(self):
        import os,copy
        from unittest.mock import patch,Mock
        from scripts.gitcode_release import publish
        expected=dict(size=1,sha256='a'*64)
        asset=dict(name='app.zip',size=1,digest='sha256:'+'a'*64,browser_download_url='https://gitcode.com/project/releases/download/v-test/app.zip')
        cached=dict(name='app.zip',size=1,sha256='a'*64,url=asset['browser_download_url'])
        for field,value,skip in ((None,None,True),('url','https://other.test/app.zip',False),('sha256','b'*64,False),('size',2,False)):
            with tempfile.TemporaryDirectory() as d:
                previous=os.getcwd()
                try:
                    os.chdir(d);Path('out').mkdir();record=copy.deepcopy(cached)
                    if field:record[field]=value
                    Path('out/gitcode-verified-v-test.json').write_text(json.dumps(dict(files=[record])))
                    client=Mock();client.repository='/repos/test';client.config={'repository_url':'https://gitcode.com/project'}
                    client.api.side_effect=[[{'tag_name':'v-test'}],{'assets':[asset]},{}]
                    with patch('scripts.gitcode_release.GitCode',return_value=client),patch('scripts.gitcode_release.anonymous_digest',return_value=('a'*64,1)) as download:
                        publish([],'v-test',prepared={'files':{'app.zip':expected}})
                        self.assertEqual(download.call_count,0 if skip else 1)
                finally:os.chdir(previous)

    def test_network_retries_never_repeat_mutating_api_calls(self):
        import io
        from unittest.mock import patch,Mock
        from scripts.gitcode_release import GitCode
        client=object.__new__(GitCode);client._headers={};client.base='https://api.gitcode.com/api/v5';client.opener=Mock()
        client.opener.open.side_effect=[TimeoutError(),io.BytesIO(b'{}')]
        with patch('scripts.gitcode_release.time.sleep'):self.assertEqual(client.api('/test'),{})
        self.assertEqual(client.opener.open.call_count,2)
        client.opener.open.reset_mock();client.opener.open.side_effect=TimeoutError()
        with self.assertRaises(RuntimeError):client.api('/test',{},'POST')
        self.assertEqual(client.opener.open.call_count,1)

if __name__=='__main__':unittest.main()
