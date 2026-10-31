import copy,unittest
from unittest.mock import Mock
from mapmatching.distribution import PRIMARY_RELEASE,FALLBACK_RELEASE,load_release,load_map_catalog,official_download

BASE='https://gitcode.com/weixin_51917701/crypticNotes/releases/download/v1/'
class DistributionTests(unittest.TestCase):
    def test_primary_is_public_gitcode_and_fallback_only_on_failure(self):
        release={'assets':[]};fetch=Mock(return_value=release)
        self.assertIs(load_release(fetch),release);fetch.assert_called_once_with(PRIMARY_RELEASE)
        fetch=Mock(side_effect=[OSError('offline'),release]);self.assertIs(load_release(fetch),release)
        self.assertEqual([c.args[0] for c in fetch.call_args_list],[PRIMARY_RELEASE,FALLBACK_RELEASE])
    def test_map_urls_use_same_release_and_hashes_remain_unchanged(self):
        specs={p:dict(asset=p+'.zip',url='https://github.com/HenryChen27/crypticNotes/releases/download/v1/'+p+'.zip',size=7,sha256='a'*64) for p in ('lianghapi','zhanshi')}
        catalog={**specs['lianghapi'],'providers':specs};original=copy.deepcopy(catalog)
        release={'assets':[dict(name='matching-module.json',browser_download_url=BASE+'matching-module.json')]+[dict(name=p+'.zip',browser_download_url=BASE+p+'.zip',size=7,digest='sha256:'+'a'*64) for p in specs]}
        result=load_map_catalog(Mock(side_effect=[release,catalog]))
        for provider,spec in result['providers'].items():
            self.assertEqual(spec['url'],BASE+provider+'.zip');self.assertEqual(spec['sha256'],'a'*64)
        self.assertEqual(catalog,original)
        release['assets'][1]['digest']='sha256:'+'b'*64
        with self.assertRaises(ValueError):load_map_catalog(Mock(side_effect=[release,catalog]))
    def test_downloads_are_scoped_to_official_repositories(self):
        self.assertTrue(official_download(BASE+'app.zip'))
        self.assertTrue(official_download('https://github.com/HenryChen27/crypticNotes/releases/download/v1/app.zip'))
        for url in ('http://gitcode.com/weixin_51917701/crypticNotes/releases/download/v1/app.zip',BASE+'../../elsewhere.zip',BASE+'%2e%2e/elsewhere.zip','https://gitcode.com.evil.test/weixin_51917701/crypticNotes/releases/download/v1/app.zip','https://gitcode.com/other/repo/releases/download/v1/app.zip'):
            self.assertFalse(official_download(url),url)
