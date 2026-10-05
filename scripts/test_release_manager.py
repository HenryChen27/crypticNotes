import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import release_manager as manager

class ReleaseTests(unittest.TestCase):
    def test_android_uses_highest_published_version(self):
        text,code,name=manager.bump_android("versionCode 21\nversionName '0.6.13-preview'",25,'0.7.1-preview')
        self.assertEqual((code,name),(26,'0.7.2-preview'))
        self.assertIn('versionCode 26',text)

    def test_local_bump(self):
        _,code,name=manager.bump_android("versionCode 21\nversionName '0.6.13-preview'")
        self.assertEqual((code,name),(22,'0.6.14-preview'))

    def test_resume_does_not_delete_already_matching_or_other_assets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.zip';p.write_bytes(b'package');sha=manager.digest(p)
            class Fake:
                def api(self,path,data=None,method=None):
                    assert method is None, 'Idempotent publication must not mutate remote files'
                    return {'id':1,'html_url':'release','assets':[
                        {'name':'sample.zip','digest':'sha256:'+sha},
                        {'name':'unselected.apk','digest':'sha256:other'}]}
            manager.publish(Fake(),{'id':'test','files':{'sample.zip':sha}},Path(d))

    def test_changed_artifact_stops_before_upload(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'sample.zip').write_bytes(b'changed')
            class Fake:
                def api(self,*args,**kwargs):return {'id':1,'assets':[]}
            with self.assertRaisesRegex(RuntimeError,'Artifact changed'):
                manager.publish(Fake(),{'id':'test','files':{'sample.zip':'wrong'}},Path(d))

if __name__=='__main__':unittest.main()
