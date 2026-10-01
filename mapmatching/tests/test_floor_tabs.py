import unittest
from pathlib import Path
import cv2
import numpy as np
from mapmatching.src.floor_tabs import inspect_floor_tabs


def tab_frame(selected, nightmare=True):
    frame = np.full((720, 1280, 3), 30, np.uint8)
    root = Path(__file__).resolve().parents[1]/'assets/map-ui'
    for floor, cx in ((-1, 940), (1, 1000), (2, 1060)):
        if floor == -1 and not nightmare:
            continue
        frame[62:102, cx-28:cx+28] = 100 if floor == selected else 40
        digit = cv2.imread(str(root/f'floor-{abs(floor)}.png'), 0)
        digit = cv2.resize(digit, (6 if abs(floor)==1 else 14, 26), interpolation=cv2.INTER_NEAREST)
        x = cx-digit.shape[1]//2+(6 if floor==-1 else 0)
        patch = frame[69:95, x:x+digit.shape[1]]
        patch[digit>0] = 205
        if floor == -1:
            frame[82:85, cx-13:cx-3] = 205
    return frame


class FloorTabsTests(unittest.TestCase):
    def test_layouts_and_video_transforms(self):
        for nightmare in (False, True):
            for floor in ((-1,1,2) if nightmare else (1,2)):
                base = tab_frame(floor, nightmare)
                for scale in (.8,1.,1.5,2.):
                    frame = cv2.resize(base, None, fx=scale, fy=scale)
                    frame = cv2.copyMakeBorder(frame, 20,20,24,24,cv2.BORDER_CONSTANT)
                    frame = cv2.GaussianBlur(frame,(3,3),.6)
                    frame = cv2.imdecode(cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,65])[1],1)
                    with self.subTest(nightmare=nightmare,floor=floor,scale=scale):
                        self.assertEqual(inspect_floor_tabs(frame)['floor'],floor)

    def test_unknown_and_ambiguous(self):
        self.assertIsNone(inspect_floor_tabs(tab_frame(None))['floor'])
        self.assertIsNone(inspect_floor_tabs(np.full((720,1280,3),100,np.uint8))['floor'])
        frame = tab_frame(1)
        frame[62:102,1032:1088] = frame[62:102,972:1028]
        self.assertIsNone(inspect_floor_tabs(frame)['floor'])

    def test_existing_screenshots(self):
        root = Path(__file__).resolve().parents[2]
        frame = cv2.imdecode(np.frombuffer((root/'examples/1/example.png').read_bytes(),np.uint8),1)
        self.assertEqual(inspect_floor_tabs(frame)['floor'],1)
        for path in (root/'out/android-samples').glob('closed-*.jpg'):
            self.assertIsNone(inspect_floor_tabs(cv2.imread(str(path)))['floor'])


if __name__ == '__main__':
    unittest.main()
