import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import release_manager as manager

class ReleaseTests(unittest.TestCase):
    def test_release_notes_reuse_popup_copy_for_selected_platforms(self):
        source=manager.ROOT/'mapmatching/assets/update-news.json'
        import json
        news=json.loads(source.read_text(encoding='utf8'))
        windows=manager.read_notes(source,{'windows'})
        android=manager.read_notes(source,{'android'})
        combined=manager.read_notes(source,{'android','windows'})
        self.assertEqual(windows,android);self.assertEqual(android,combined)
        self.assertEqual(combined.splitlines()[2:],[f"1. **{news['important']}**",*(f'{index}. {item}' for index,item in enumerate(news['changes'],2))])
        with tempfile.TemporaryDirectory() as directory:
            plain=Path(directory)/'notes.md';plain.write_text('原样保留\n',encoding='utf8')
            self.assertEqual(manager.read_notes(plain,{'android'}),'原样保留\n')
            platform=plain.with_suffix('.json');platform.write_text(json.dumps(dict(changes=['通用'],desktop='电脑',android='手机')),encoding='utf8')
            self.assertEqual(manager.read_notes(platform,{'windows'}).splitlines()[2:],['1. 通用','2. 电脑'])
            self.assertEqual(manager.read_notes(platform,{'android'}).splitlines()[2:],['1. 通用','2. 手机'])

    def test_unchanged_publication_returns_before_sync_and_build(self):
        with tempfile.TemporaryDirectory() as d:
            class Fake:
                def api(self,path):
                    return {'id':1,'assets':[{'name':'app.apk','digest':'sha256:correct'}]}
                def manifest(self,release,name):
                    return {'input':manager.input_fingerprint('android'),
                            'packages':{'app.apk':'correct'}}
            with patch.object(manager,'ROOT',Path(d)), patch.object(manager,'GitHub',return_value=Fake()), \
                 patch.object(manager,'sync_sources') as sync, patch.object(manager,'run') as run, \
                 patch('sys.argv',['release_manager','--platforms','android','--publish']):
                manager.main()
                sync.assert_not_called();run.assert_not_called()
                self.assertEqual(list(Path(d).iterdir()),[])

    def test_fingerprints_follow_platform_inputs_not_versions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/'android/app/build.gradle';p.parent.mkdir(parents=True)
            p.write_text("versionCode 21\nversionName '0.6.13-preview'", encoding='utf-8')
            ui=root/'mapmatching/ui.py';ui.parent.mkdir();ui.write_text('old')
            before={platform:manager.input_fingerprint(platform,root) for platform in manager.PACKAGES}
            p.write_text("versionCode 22\nversionName '0.6.14-preview'", encoding='utf-8')
            self.assertEqual(before['android'],manager.input_fingerprint('android',root))
            ui.write_text('new')
            self.assertEqual(before['android'],manager.input_fingerprint('android',root))
            self.assertNotEqual(before['windows'],manager.input_fingerprint('windows',root))
            shared=root/'maps/nightmare/test.jpg';shared.parent.mkdir(parents=True);shared.write_bytes(b'map')
            for platform in manager.PACKAGES:
                self.assertNotEqual(before[platform],manager.input_fingerprint(platform,root))

    def test_skip_requires_matching_source_and_verified_artifacts(self):
        current={'schema':1,'sha256':'source'}
        baseline={'input':current,'packages':{'app.apk':'correct'}}
        self.assertTrue(manager.unchanged(current,baseline,{'app.apk':'correct'}))
        self.assertFalse(manager.unchanged(current,baseline,{'app.apk':'wrong'}))
        self.assertFalse(manager.unchanged(current,baseline,{}))
        self.assertFalse(manager.unchanged(current,{},{}))
        self.assertFalse(manager.unchanged({'sha256':'changed'},baseline,{'app.apk':'correct'}))

    def test_menu_retries_bad_input_then_selects_platforms(self):
        import argparse
        args=argparse.Namespace(platforms=None,publish=False,notes=None,resume=None)
        with patch('builtins.input',side_effect=['bad','1','8','2','1 2','']):
            self.assertTrue(manager.interactive(args))
        self.assertEqual(args.platforms,['windows','android'])
        self.assertTrue(args.publish)

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
            with patch.object(manager,'mirror_after_publish'):
                manager.publish(Fake(),{'id':'test','files':{'sample.zip':sha}},Path(d))

    def test_changed_artifact_stops_before_upload(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'sample.zip').write_bytes(b'changed')
            class Fake:
                def api(self,*args,**kwargs):return {'id':1,'assets':[]}
            with self.assertRaisesRegex(RuntimeError,'Artifact changed'):
                manager.publish(Fake(),{'id':'test','files':{'sample.zip':'wrong'}},Path(d))

if __name__=='__main__':unittest.main()

class StaleSourceTests(unittest.TestCase):
    def test_moved_maps_leave_the_public_tree_in_short_chunks(self):
        exported=['maps/curse/lianghapi/hard/a.webp','scripts/release_manager.py','docs/releasing.md']
        published=['maps/lianghapi/hard/a.webp','maps/curse/lianghapi/hard/a.webp','maps/hard/老图.jpg',
                   'scripts/release_manager.py','.github/workflows/macos.yml','README.md','']
        chunks=manager.stale_sources(exported,published,size=1)
        self.assertEqual(chunks,[['maps/hard/老图.jpg'],['maps/lianghapi/hard/a.webp']])
        self.assertEqual(manager.stale_sources(exported,exported),[])
