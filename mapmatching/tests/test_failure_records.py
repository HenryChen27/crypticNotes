import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import cv2
from mapmatching.src.failure_records import FailureRecorder, category


class FailureRecordTests(unittest.TestCase):
    def test_lossless_image_context_and_duplicate_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            r = FailureRecorder(Path(temp)/'records', temp, max_cases=1)
            pixels = np.full((30,40,3), 91, np.uint8)
            r.save(pixels, {'candidates':[]}, {'difficulty':'hard'}, 'failed')
            records = list(r.directory.glob('*/*/record.json'))
            self.assertEqual(len(records), 1)
            data = json.loads(records[0].read_text(encoding='utf-8'))
            self.assertEqual(data['context']['difficulty'], 'hard')
            image = cv2.imdecode(np.frombuffer((records[0].parent/'screen.png').read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(image, pixels)
            r.save(pixels, {}, {}, 'duplicate')
            r.save(pixels+1, {}, {}, 'exception', error='error')
            self.assertEqual(len(list(r.directory.glob('*/*/record.json'))),1)

    def test_classification_uses_the_display_rejection_order(self):
        c = dict(pose={'scale':1}, explained=.8, contradiction=.1, retrieval_score=8, floor=1)
        self.assertEqual(category({'candidates':[dict(c,pose=None)]}), '无法配准')
        self.assertEqual(category({'candidates':[dict(c,explained=.3)]}), '匹配证据不足')
        self.assertEqual(category({'candidates':[c,c]}), '候选地图相似')
        self.assertEqual(category({'candidates':[dict(c,floor=None)]}), '楼层不确定')
        self.assertEqual(category({},'exception'), '程序异常')

    def test_unwritable_target_does_not_raise(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'file';target.write_text('occupied')
            r = FailureRecorder(target,temp)
            self.assertIn('失败',r.save(np.zeros((4,4,3),np.uint8),{},{},'failed'))
