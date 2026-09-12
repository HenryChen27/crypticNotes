"""Hypothesis test: axis-aligned stable wall segments, not fog contours."""
from pathlib import Path
import json
import cv2
import numpy as np
from scipy.optimize import minimize
from .semantic_probe import classes
from mapmatching.src.evidence import extract
from mapmatching.src.reference import read_image
from mapmatching.src import mapstore


def walls(image: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lines = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    points = []
    maps = [np.zeros(gray.shape, np.uint8), np.zeros(gray.shape, np.uint8)]
    support = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    if lines is not None:
        for line in lines[:, 0]:
            a, b = line[:2], line[2:]
            length = np.linalg.norm(a-b)
            delta = np.abs(a-b)
            if length < 9 or min(delta)/max(delta) > .06:
                continue
            orientation = 0 if delta[0] > delta[1] else 1
            sample = np.linspace(a, b, max(2, int(length/2))).round().astype(int)
            sample[:, 0] = sample[:, 0].clip(0, gray.shape[1]-1)
            sample[:, 1] = sample[:, 1].clip(0, gray.shape[0]-1)
            valid = (support[sample[:, 1], sample[:, 0]] > 0) & (hsv[sample[:, 1], sample[:, 0], 1] < 100)
            if np.mean(valid) < .8:
                continue
            cv2.line(maps[orientation], tuple(a.round().astype(int)), tuple(b.round().astype(int)), 1, 1)
            points.extend([(float(x), float(y), orientation) for x, y in sample[valid]])
    return np.asarray(points, np.float32).reshape(-1, 3), [cv2.distanceTransform(1-m, cv2.DIST_L2, 3) for m in maps]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root/'out/mapmatching'
    report = json.loads((out/'baseline.json').read_text(encoding='utf-8'))
    # source 在 floors.json（登记表）里，不在 index.json（特征缓存）里。
    refs = {e['map_id']: e for e in mapstore.read_manifest(mapstore.maps_dir(root))}
    cache, rows = {}, []
    for sample in report['samples']:
        image = read_image(root/sample['screenshot'])
        ev = extract(image)
        small = cv2.resize(image, (ev.mask.shape[1], ev.mask.shape[0]), interpolation=cv2.INTER_AREA)
        gp, _ = walls(small, ev.mask)
        labels = classes(small)
        labels[cv2.erode(ev.mask, np.ones((5, 5), np.uint8)) == 0] = 0
        cy, cx = np.nonzero(labels)
        cp = np.column_stack((cx, cy)).astype(np.float32)
        candidates = []
        for candidate in sample['candidates']:
            key = candidate['map_id']
            if key not in cache:
                raw = read_image(root/refs[key]['source'])
                re = extract(raw, reference=True)
                rr = cv2.resize(raw, (re.mask.shape[1], re.mask.shape[0]), interpolation=cv2.INTER_AREA)
                cache[key] = (re, walls(rr, re.mask)[1], classes(raw))
            re, dt, rlabels = cache[key]
            p = candidate['pose']
            if p is None or not len(gp):
                continue
            s = p['scale']*ev.image_factor/re.image_factor
            initial = np.array([s, p['tx']*ev.image_factor, p['ty']*ev.image_factor])
            def distances(pose):
                ss, tx, ty = pose
                xy = ((gp[:, :2]-[tx, ty])/ss).astype(np.float32)
                ds = np.zeros(len(gp))
                for direction in (0, 1):
                    select = gp[:, 2] == direction
                    if np.any(select):
                        ds[select] = cv2.remap(dt[direction], xy[select, 0, None], xy[select, 1, None], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=1000).ravel()*ss
                return ds
            before = float(np.mean(np.exp(-.5*(distances(initial)/1.5)**2)))
            fit = minimize(lambda pose: float(np.minimum(distances(pose), 5).mean()), initial, method='Powell', bounds=[(s*.95, s*1.05), (initial[1]-6, initial[1]+6), (initial[2]-6, initial[2]+6)], options={'maxiter': 20, 'xtol': .002, 'ftol': .0001})
            pose = fit.x
            score = float(np.mean(np.exp(-.5*(distances(pose)/1.5)**2)))
            xy = ((cp-pose[1:])/pose[0]/re.image_factor).astype(np.float32)
            rl = cv2.remap(rlabels, xy[:, 0, None], xy[:, 1, None], cv2.INTER_NEAREST).ravel()
            class_match = float(np.mean(rl == labels[cy, cx]))
            candidates.append({'map_id': key, 'boundary': candidate['explained'], 'wall_score': before, 'refined_wall_score': score, 'refined_class_score': class_match, 'product': score*class_match, 'refined_pose': {'scale': float(pose[0]*re.image_factor/ev.image_factor), 'tx': float(pose[1]/ev.image_factor), 'ty': float(pose[2]/ev.image_factor)}})
        rows.append({'screenshot': sample['screenshot'], 'gt_map': sample['gt_map'], 'game_wall_points': len(gp), 'candidates': candidates})
    (out/'wall_refine_probe.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
