"""Locate label bands and framed insets for offline metadata review only."""
from pathlib import Path
import json
import cv2
import numpy as np
from mapmatching.src.reference import read_image
from mapmatching.src import mapstore


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    # difficulty/source/sha256 现在只在 floors.json 里，index.json 只剩特征指针。
    manifest = mapstore.read_manifest(mapstore.maps_dir(root))
    rows = []
    for record in manifest:
        if record['difficulty'] != 'hard':
            continue
        raw = read_image(root/record['source'])
        hsv = cv2.cvtColor(raw, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        bright = (((h<40)&(s>90)&(v>170))|((s<40)&(v>180))).astype(np.uint8)
        counts = bright[:, :120].sum(axis=1)
        ys = np.flatnonzero(counts>8)
        groups = np.split(ys, np.flatnonzero(np.diff(ys)>12)+1)
        bands = [[int(g[0]), int(g[-1]), int(counts[g].sum())] for g in groups if len(g)>10 and counts[g].sum()>500]
        white = ((s<50)&(v>180)).astype(np.uint8)
        contours, _ = cv2.findContours(white, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        insets = []
        for contour in contours:
            x,y,w,hh = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if w>100 and hh>100 and area/(w*hh)>.8 and (x<25 or x+w>raw.shape[1]-25):
                box = [x,y,x+w,y+hh]
                if not any(abs(x-b[0])+abs(y-b[1])<10 for b in insets):
                    insets.append(box)
        rows.append({'map_id': record['map_id'], 'source': record['source'], 'source_sha256': record['sha256'], 'size': [raw.shape[1], raw.shape[0]], 'label_bands': bands, 'framed_insets': insets})
    (root/'out/mapmatching/floor_probe.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
