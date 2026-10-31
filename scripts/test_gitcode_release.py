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

if __name__=='__main__':unittest.main()
