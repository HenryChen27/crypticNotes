"""Evaluate local corridor/room evidence on saved poses, without changing them."""
from pathlib import Path
import json
import cv2
import numpy as np
from mapmatching.src.evidence import extract
from mapmatching.src.reference import read_image
from mapmatching.src import mapstore


def classes(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    valid = (v >= 78) & (v <= 170) & (s >= 20) & (s <= 100)
    labels = np.zeros(h.shape, np.uint8)
    labels[valid & (h >= 108) & (h <= 125)] = 1
    labels[valid & (h <= 30)] = 2
    return labels


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root/'out/mapmatching'
    report = json.loads((out/'baseline.json').read_text(encoding='utf-8'))
    # source 在 floors.json（登记表）里，不在 index.json（特征缓存）里。
    refs = {e['map_id']: e for e in mapstore.read_manifest(mapstore.maps_dir(root))}
    results, sheets = [], []
    for i, sample in enumerate(report['samples']):
        image = read_image(root/sample['screenshot'])
        ev = extract(image)
        small = cv2.resize(image, (ev.mask.shape[1], ev.mask.shape[0]), interpolation=cv2.INTER_AREA)
        labels = classes(small)
        interior = cv2.erode(ev.mask, np.ones((5, 5), np.uint8)) > 0
        # Only observed interiors; no reverse/reference coverage term.
        labels[~interior] = 0
        yy, xx = np.nonzero(labels)
        xy = np.column_stack((xx, yy)).astype(float)
        panel_images = [('Observed', small)]
        rows = []
        for j, candidate in enumerate(sample['candidates']):
            raw = read_image(root/refs[candidate['map_id']]['source'])
            rlabels = classes(raw)
            p = candidate['pose']
            if p is None:
                continue
            coords = ((xy/ev.image_factor-[p['tx'], p['ty']])/p['scale']).astype(np.float32)
            rl = cv2.remap(rlabels, coords[:, 0, None], coords[:, 1, None], cv2.INTER_NEAREST).ravel()
            gl = labels[yy, xx]
            correct = float(np.mean(rl == gl))
            conflict = float(np.mean((rl > 0) & (rl != gl)))
            matched = {str(c): float(np.mean(rl[gl == c] == c)) if np.any(gl == c) else None for c in [1, 2]}
            rows.append({'map_id': candidate['map_id'], 'boundary': candidate['explained'], 'class_match': correct, 'class_conflict': conflict, 'per_class': matched})
            if j == 0 or candidate['map_id'] == sample['gt_map']:
                affine = np.array([[p['scale']*ev.image_factor, 0, p['tx']*ev.image_factor], [0, p['scale']*ev.image_factor, p['ty']*ev.image_factor]])
                aligned = cv2.warpAffine(raw, affine, (small.shape[1], small.shape[0]))
                panel_images.append(('Best' if j == 0 else 'GT diagnostic', aligned))
        results.append({'screenshot': sample['screenshot'], 'gt_map': sample['gt_map'], 'candidates': rows})
        n, _, stats, _ = cv2.connectedComponentsWithStats(ev.mask, 8)
        largest = stats[1:][np.argmax(stats[1:, cv2.CC_STAT_AREA])]
        x, y, w, h = largest[:4]
        x, y, w, h = max(0, x-15), max(0, y-15), w+30, h+30
        tiles = []
        for label, pic in panel_images:
            crop = pic[y:y+h, x:x+w]
            factor = min(475/crop.shape[1], 325/crop.shape[0])
            crop = cv2.resize(crop, None, fx=factor, fy=factor)
            tile = np.zeros((360, 480, 3), np.uint8)
            tile[30:30+crop.shape[0], :crop.shape[1]] = crop
            cv2.putText(tile, f'{i}: {label}', (5, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
            tiles.append(tile)
        while len(tiles)<3:
            tiles.append(np.zeros_like(tiles[0]))
        sheets.append(np.hstack(tiles))
    (out/'semantic_probe.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    cv2.imencode('.jpg', np.vstack(sheets))[1].tofile(out/'rgb_diagnostics.jpg')
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
