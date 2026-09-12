"""Coordinate rulers for independent manual landmark annotation.

Only raw paired files and manually chosen view boxes are used; no matcher,
predicted transforms or cache are imported. Output is evaluation tooling only.
"""
from pathlib import Path
import json
import cv2
import numpy as np

VIEWS = [
    ('ref_t', 'examples/0/北-T门.jpg', (140, 470, 490, 680), 2.),
    ('ref_1', 'examples/3/北-1门.jpg', (260, 540, 580, 705), 2.5),
    ('ref_l', 'examples/4/右-双L门.jpg', (170, 500, 530, 750), 2.),
    ('ref_d', 'examples/5/左-对角门.png', (230, 425, 460, 750), 2.),
    ('game_0', 'examples/0/example.png', (900, 680, 1370, 855), 2.),
    ('game_1', 'examples/1/example2.png', (1150, 850, 2100, 1200), 1.),
    ('game_2', 'examples/2/example.png', (1260, 650, 2170, 950), 1.),
    ('game_3', 'examples/3/example.png', (1000, 720, 1540, 950), 1.5),
    ('game_4', 'examples/4/example.png', (1230, 460, 1780, 850), 1.5),
    ('game_5', 'examples/5/example.png', (1230, 270, 1630, 810), 1.5),
]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root/'out/mapmatching/annotation_views'
    out.mkdir(exist_ok=True)
    for name, source, box, scale in VIEWS:
        raw = cv2.imdecode(np.fromfile(root/source, np.uint8), cv2.IMREAD_COLOR)
        x0, y0, x1, y1 = box
        crop = cv2.resize(raw[y0:y1, x0:x1], None, fx=scale, fy=scale)
        pic = cv2.copyMakeBorder(crop, 30, 0, 45, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        for x in range((x0//20+1)*20, x1, 20):
            sx = int((x-x0)*scale)+45
            cv2.line(pic, (sx, 25), (sx, pic.shape[0]-1), (70, 90, 70), 1)
            cv2.putText(pic, str(x), (sx-12, 20), cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 0, 0), 1)
        for y in range((y0//20+1)*20, y1, 20):
            sy = int((y-y0)*scale)+30
            cv2.line(pic, (40, sy), (pic.shape[1]-1, sy), (70, 90, 70), 1)
            cv2.putText(pic, str(y), (1, sy+3), cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 0, 0), 1)
        cv2.imencode('.png', pic)[1].tofile(out/f'{name}.png')
    (out/'views.json').write_text(json.dumps(VIEWS, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
