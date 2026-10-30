import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mapmatching.src import ui_trace

class TraceTests(unittest.TestCase):
    def test_health_does_not_evict_matching_events(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ui_trace,'record_directory',Path(d)),patch.object(ui_trace,'HEALTH_LIMIT',1):
            ui_trace.trace('overlay_displayed',token=1)
            for i in range(10):ui_trace.trace('keyboard_health',count=i)
            events=(Path(d)/'ui-events.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual([json.loads(x)['event'] for x in events],['overlay_displayed'])
            self.assertTrue((Path(d)/'input-health.previous.jsonl').exists())
    def test_rotation_keeps_previous_events(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ui_trace,'record_directory',Path(d)),patch.object(ui_trace,'EVENT_LIMIT',1):
            ui_trace.trace('worker_request',token=1)
            ui_trace.trace('worker_result',token=1)
            self.assertEqual(json.loads((Path(d)/'ui-events.previous.jsonl').read_text(encoding='utf-8'))['event'],'worker_request')
            self.assertEqual(json.loads((Path(d)/'ui-events.jsonl').read_text(encoding='utf-8'))['event'],'worker_result')
if __name__=='__main__':unittest.main()
