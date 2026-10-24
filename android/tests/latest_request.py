"""Latest-only cancellation without parallel matching or native thread interruption."""
import sys,unittest,threading
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1]/'app/src/main/python')]
import mobile_cancellation as cancel
import mobile_matching
import mobile_bridge
class Counter:
    def __init__(self):self.value=1
    def get(self):return self.value
class LatestRequestTests(unittest.TestCase):
    def test_superseded_before_start_skips_match(self):
        counter=Counter();counter.value=2
        with patch.object(mobile_bridge,'_match') as work:
            import json
            result=json.loads(mobile_bridge.match(b'', 'unused',request_counter=counter,request_serial=1))
        self.assertTrue(result['cancelled']);work.assert_not_called()
    def test_superseded_native_step_stops_before_next_candidate(self):
        counter=Counter();calls=[]
        def native(*args):calls.append('native');counter.value=2;return object()
        with cancel.request_scope():
            with self.assertRaises(cancel.Superseded):
                with cancel.request_scope(counter,1),patch.object(mobile_matching,'_register',side_effect=native):
                    for i in range(10):mobile_matching.register(None,None)
        self.assertEqual(calls,['native'])
        cancel.checkpoint() # scope restored even after cancellation
    def test_multiple_clicks_keep_only_latest(self):
        counter=Counter();counter.value=5
        for serial in (1,2,3,4):
            with self.assertRaises(cancel.Superseded),cancel.request_scope(counter,serial):pass
        with cancel.request_scope(counter,5):cancel.checkpoint()
    def test_inspection_thread_is_not_cancelled(self):
        counter=Counter();counter.value=2;errors=[]
        with self.assertRaises(cancel.Superseded):
            with cancel.request_scope(counter,2):
                counter.value=3
                def inspect():
                    try:cancel.checkpoint()
                    except Exception as e:errors.append(e)
                t=threading.Thread(target=inspect);t.start();t.join()
        self.assertEqual(errors,[])
    def test_default_call_remains_compatible(self):
        with patch.object(mobile_bridge,'_match',return_value='ok'):
            self.assertEqual(mobile_bridge.match(b'', 'unused'),'ok')
if __name__=='__main__':unittest.main()
