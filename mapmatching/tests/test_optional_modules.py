import io,json,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
from mapmatching.matching_module import MatchingModule
from mapmatching.minigames import read_collection,CollectionGameStore

class OptionalModulesTests(unittest.TestCase):
    def test_uninstall_preserves_custom_map_and_leaves_source_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';source=root/'source';source.mkdir()
            with patch('mapmatching.matching_module.DATA_ROOT',data),patch('mapmatching.matching_module.ROOT',source),patch('mapmatching.matching_module.FROZEN',False),patch('mapmatching.src.mapstore.build_index'):
                store=MatchingModule();maps=store.folder/'maps';maps.mkdir(parents=True)
                entries=[{'map_id':'official','source':'maps/official.jpg'},{'map_id':'custom','source':'maps/custom.jpg'}]
                (maps/'floors.json').write_text(json.dumps({'references':entries}))
                (maps/'disabled.json').write_text('{"records":[]}')
                (maps/'official-library.json').write_text(json.dumps({'ids':['official'],'files':['official.jpg']}))
                (maps/'official.jpg').write_bytes(b'official');(maps/'custom.jpg').write_bytes(b'personal')
                self.assertTrue(store.enabled());store.delete();self.assertFalse(store.enabled())
                self.assertFalse(store.folder.exists())
                kept=data/'module-user-data/mapmatching/maps'
                self.assertEqual((kept/'custom.jpg').read_bytes(),b'personal')
                self.assertFalse((kept/'official.jpg').exists())
                self.assertEqual(json.loads((kept/'floors.json').read_text())['references'],[entries[1]])

    def test_install_merges_preserved_maps_and_checks_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';source=root/'source';source.mkdir()
            payload=io.BytesIO()
            with zipfile.ZipFile(payload,'w') as z:
                z.writestr('maps/floors.json','{"references":[]}');z.writestr('maps/disabled.json','{"records":[]}')
            raw=payload.getvalue();spec={'url':'https://github.com/HenryChen27/crypticNotes/releases/download/v1/module.zip','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            with patch('mapmatching.matching_module.DATA_ROOT',data),patch('mapmatching.matching_module.ROOT',source):
                store=MatchingModule()
                with patch('mapmatching.matching_module.urllib.request.urlopen',side_effect=[io.BytesIO(json.dumps(spec).encode()),io.BytesIO(raw)]):store.download(lambda *a:None)
                self.assertTrue(store.enabled());self.assertEqual(store.root(),store.folder)
                spec['sha256']='0'*64
                with patch('mapmatching.matching_module.urllib.request.urlopen',side_effect=[io.BytesIO(json.dumps(spec).encode()),io.BytesIO(raw)]),self.assertRaises(ValueError):store.download(lambda *a:None)
                self.assertTrue(store.enabled())

    def test_kitchen_title_does_not_fall_back_to_english_id(self):
        from mapmatching.minigames import game_title,GameStore
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(game_title('mini-kitchen','mini-kitchen'),'邦邦小厨房')
            self.assertEqual(GameStore(tmp,'mini-kitchen').title,'邦邦小厨房')
            self.assertEqual(CollectionGameStore(tmp,{'id':'mini-kitchen','name':'Mini Kitchen'}).title,'邦邦小厨房')
            self.assertEqual(game_title('new-game','新游戏'),'新游戏')

    def test_library_version_reads_installed_module(self):
        with tempfile.TemporaryDirectory() as tmp,patch('mapmatching.matching_module.DATA_ROOT',Path(tmp)):
            store=MatchingModule();store.folder.mkdir(parents=True)
            (store.folder/'maps').mkdir();(store.folder/'maps/floors.json').write_text('{"references":[]}')
            (store.folder/'module.json').write_text(json.dumps({'sha256':'abc123456789'+'0'*52}))
            self.assertEqual(store.version(),'库-abc123456789')
            (store.folder/'module.json').write_text(json.dumps({'version':'1.2.3'}))
            self.assertEqual(store.version(),'1.2.3')

    def test_collection_rejects_untrusted_package(self):
        spec={'id':'jellyfish','runtime':'system-webview','entry':'game/index.html','url':'https://evil.example/game.zip','size':1,'sha256':'a'*64}
        raw=json.dumps({'schema':1,'games':{'jellyfish':spec}}).encode()
        with patch('mapmatching.minigames.urllib.request.urlopen',return_value=io.BytesIO(raw)),self.assertRaises(ValueError):read_collection()

    def test_games_have_separate_install_identity_and_hash_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=CollectionGameStore(tmp,{'id':'jellyfish','sha256':'a'*64});b=CollectionGameStore(tmp,{'id':'minesweeper','sha256':'b'*64})
            self.assertNotEqual(a.folder,b.folder)
            a.folder.mkdir();(a.folder/'package.json').write_text(json.dumps({'downloadSha256':'a'*64}))
            self.assertFalse(a.update_available());self.assertTrue(b.update_available())
