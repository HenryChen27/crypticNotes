import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from mapmatching.update_notice import newer_build


class UpdateNoticeTests(unittest.TestCase):
    def test_newer_same_older_and_partial_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'windows-build.json').write_text(json.dumps({'build':100}),encoding='utf-8')
            release={'assets':[
                {'name':'windows-update.json','browser_download_url':'https://example.com/manifest'},
                {'name':'IdentityVMapAssistant-Windows-x64.zip','size':12,'digest':'sha256:abcd'}]}
            for build,size,digest,expected in ((101,12,'abcd',True),(100,12,'abcd',False),
                    (99,12,'abcd',False),(101,13,'abcd',False),(101,12,'efgh',False)):
                fetch=Mock(side_effect=[release,{'build':build,'size':size,'sha256':digest}])
                self.assertEqual(newer_build(root,fetch),expected)
                self.assertEqual(fetch.call_count,2)

    def test_source_checkout_has_no_false_update(self):
        with tempfile.TemporaryDirectory() as folder:
            fetch=Mock()
            self.assertFalse(newer_build(Path(folder),fetch))
            fetch.assert_not_called()
