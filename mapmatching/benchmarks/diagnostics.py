"""Evaluation-only side-by-side binary geometry sheets, never game overlays."""
from pathlib import Path
import json
import cv2
import numpy as np
from mapmatching.src.reference import load, read_image
from mapmatching.src.evidence import extract


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root/'out/mapmatching'
    refs = {r.map_id: r for r in load(root/'maps')}
    report = json.loads((output/'baseline.json').read_text(encoding='utf-8'))
    sheets = []
    for i, sample in enumerate(report['samples']):
        ev = extract(read_image(root/sample['screenshot']))
        yy, xx = np.nonzero(ev.mask)
        if not len(xx):
            continue
        x0, y0 = max(0, xx.min()-10), max(0, yy.min()-10)
        x1, y1 = min(ev.mask.shape[1], xx.max()+11), min(ev.mask.shape[0], yy.max()+11)
        panels = [('Observed', ev.mask)]
        for label, candidate in [('Ranked first', sample['candidates'][0]), ('GT-map diagnostic', sample['oracle_registration_diagnostic_only'])]:
            ref = refs[candidate['map_id']]
            p = candidate['pose']
            if p is None:
                mask = np.zeros_like(ev.mask)
            else:
                s = p['scale']*ev.image_factor/ref.evidence.image_factor
                affine = np.array([[s, 0, p['tx']*ev.image_factor], [0, s, p['ty']*ev.image_factor]])
                mask = cv2.warpAffine(ref.evidence.mask, affine, (ev.mask.shape[1], ev.mask.shape[0]), flags=cv2.INTER_NEAREST)
            panels.append((label, mask))
        tiles = []
        for label, mask in panels:
            tile = np.zeros((300, 400, 3), np.uint8)
            crop = mask[y0:y1, x0:x1]*255
            ratio = min(390/crop.shape[1], 260/crop.shape[0])
            crop = cv2.resize(crop, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_NEAREST)
            tile[35:35+crop.shape[0], :crop.shape[1]] = crop[:, :, None]
            cv2.putText(tile, f'{i}: {label}', (5, 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
            tiles.append(tile)
        sheets.append(np.hstack(tiles))
    cv2.imencode('.png', np.vstack(sheets))[1].tofile(output/'geometry_diagnostics.png')
    print('Wrote geometry_diagnostics.png (GT diagnostics only)')


if __name__ == '__main__':
    main()
