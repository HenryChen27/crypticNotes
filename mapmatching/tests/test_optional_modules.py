import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from mapmatching import module_payload
from mapmatching.desktop_modules import update_installed
from mapmatching.matching_module import MatchingModule
from mapmatching.minigames import read_collection, CollectionGameStore, GameStore, game_title


class OptionalModulesTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for target in ('mapmatching.matching_module.DATA_ROOT','mapmatching.desktop_modules.DATA_ROOT'):
            active=patch(target,self.root);active.start();self.addCleanup(active.stop)

    def archive(self,key,files):
        path=self.root/module_payload.ASSETS[key]
        with zipfile.ZipFile(path,'w') as bundle:
            for name,value in files.items():bundle.writestr(name,value)
        return dict(url=path.as_uri(),sha256=module_payload.digest(path),size=path.stat().st_size)

    def core(self):
        spec=self.archive('notes',{name:b'fixture' for name in module_payload.FILES['notes']})
        store=MatchingModule()
        with patch('mapmatching.matching_module.module_info',return_value=spec):store.download(lambda *_:None)
        return store,spec

    def test_author_requires_notes_and_original_is_not_an_optional_pack(self):
        self.assertFalse(MatchingModule('original').enabled())
        with self.assertRaisesRegex(ValueError,'主程序'):MatchingModule('zhanshi').download(None)
        store,_=self.core();original=MatchingModule('original')
        self.assertTrue(store.author_enabled('original'));self.assertFalse(store.author_enabled('lianghapi'))
        self.assertEqual(original.root(),self.root/'modules/notes')
        with self.assertRaises(ValueError):original.delete()
        (store.root()/'maps/curse/original/easy/art.npz').unlink();self.assertFalse(original.enabled())

    def test_delete_notes_removes_both_authors_but_preserves_personal_maps(self):
        core,_=self.core();maps=MatchingModule('lianghapi').root()/'maps';maps.mkdir(parents=True)
        custom={'map_id':'custom','source':'maps/custom.png'};(maps/'custom.png').write_bytes(b'personal')
        (maps/'floors.json').write_text(json.dumps({'references':[custom]}))
        with patch('mapmatching.src.provider_packages.build_index'):
            for author in ('lianghapi','zhanshi'):
                entry=dict(map_id=author,source='maps/'+author+'.jpg',provider=author)
                spec=self.archive(author,{'maps/floors.json':json.dumps({'references':[entry]}),entry['source']:b'official'})
                with patch('mapmatching.matching_module.module_info',return_value=spec):MatchingModule(author).download(lambda *_:None)
                self.assertTrue(core.author_enabled(author))
            core.delete()
        self.assertFalse(core.enabled());self.assertFalse(core.root().exists())
        self.assertTrue(all(not MatchingModule(author).receipt() for author in ('lianghapi','zhanshi')))
        self.assertEqual((maps/'custom.png').read_bytes(),b'personal');self.assertFalse((maps/'zhanshi.jpg').exists())
        self.assertEqual(json.loads((maps/'floors.json').read_text())['references'],[custom])

    def test_bad_update_keeps_installed_version(self):
        store,good=self.core();self.assertEqual(store.version(),good['sha256'][:12])
        for bad in (dict(good,sha256='0'*64),self.archive('notes',{'unknown.txt':'wrong'})):
            with patch('mapmatching.matching_module.module_info',return_value=bad), self.assertRaises(ValueError):store.download(lambda *_:None)
            self.assertEqual(store.receipt()['sha256'],good['sha256'])
            self.assertTrue(store.enabled())

    def test_batch_only_downloads_installed_outdated_modules(self):
        missing,latest,old=(Mock() for _ in range(3));missing.enabled.return_value=False;latest.update_available.return_value=False
        update_installed([('missing',missing),('latest',latest),('old',old)],Mock())
        missing.update_available.assert_not_called();missing.download.assert_not_called();latest.download.assert_not_called();old.download.assert_called_once()

    def test_kitchen_title_does_not_fall_back_to_english_id(self):
        self.assertEqual(game_title('mini-kitchen','mini-kitchen'),'邦邦小厨房')
        self.assertEqual(GameStore(self.root,'mini-kitchen').title,'邦邦小厨房')
        self.assertEqual(CollectionGameStore(self.root,{'id':'mini-kitchen','name':'Mini Kitchen'}).title,'邦邦小厨房')
        self.assertEqual(game_title('new-game','新游戏'),'新游戏')

    def test_collection_rejects_untrusted_package(self):
        spec={'id':'jellyfish','runtime':'system-webview','entry':'game/index.html','url':'https://evil.example/game.zip','size':1,'sha256':'a'*64}
        raw=json.dumps({'schema':1,'games':{'jellyfish':spec}}).encode()
        with patch('mapmatching.minigames.urllib.request.urlopen',return_value=io.BytesIO(raw)),self.assertRaises(ValueError):read_collection()

    def test_games_have_separate_install_identity_and_hash_updates(self):
        first=CollectionGameStore(self.root,{'id':'jellyfish','sha256':'a'*64});second=CollectionGameStore(self.root,{'id':'minesweeper','sha256':'b'*64})
        self.assertNotEqual(first.folder,second.folder)
        first.folder.mkdir();(first.folder/'package.json').write_text(json.dumps({'downloadSha256':'a'*64}))
        self.assertFalse(first.update_available());self.assertTrue(second.update_available())
