import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.export_android_legacy import preferences

class BackupTests(unittest.TestCase):
    def test_android_xml_retains_value_types(self):
        values=preferences('<map><string name="mode">duo</string><int name="opacity" value="30"/><float name="scale" value="1.2"/><boolean name="feedback" value="true"/><set name="ids"><string>x</string></set></map>')
        self.assertEqual(values['mode'],{'type':'String','value':'duo'})
        self.assertEqual(values['opacity'],{'type':'Integer','value':30})
        self.assertEqual(values['scale'],{'type':'Float','value':1.2})
        self.assertEqual(values['feedback'],{'type':'Boolean','value':True})
        self.assertEqual(values['ids'],{'type':'set','value':['x']})
    def test_unknown_xml_type_is_rejected(self):
        with self.assertRaises(ValueError):preferences('<map><unknown name="x"/></map>')

if __name__=='__main__':unittest.main()
