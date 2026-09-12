"""Independent provisional manual landmark evaluation, never inference input."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np


def fit_similarity(reference: np.ndarray, screenshot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rc, gc = reference.mean(axis=0), screenshot.mean(axis=0)
    rr, gg = reference-rc, screenshot-gc
    scale = np.sum(rr*gg)/np.sum(rr*rr)
    pose = np.r_[scale, gc-scale*rc]
    return pose, np.linalg.norm(screenshot-(scale*reference+pose[1:]), axis=1)


def evaluate(root: Path, predictions: Path, output: Path) -> dict:
    annotations_path = root/'mapmatching/data/manual_landmarks.json'
    manual = json.loads(annotations_path.read_text(encoding='utf-8'))
    report = json.loads(predictions.read_text(encoding='utf-8'))
    # Landmark coordinates belong to the audited original image, not its name.
    # Users can replace/crop an example under the same filename during testing.
    audit_path=root/'out/mapmatching/data_audit.json'
    audited={r['path']:r['sha256'] for r in json.loads(audit_path.read_text(encoding='utf-8'))['images']} if audit_path.exists() else {}
    rows, skipped = [], []
    for sample in report['samples']:
        ann = next((a for a in manual['samples'] if a['screenshot'] == sample['screenshot']),None)
        if ann is None:
            skipped.append({'screenshot':sample['screenshot'],'reason':'no independent manual landmarks'})
            continue
        expected_hash=ann.get('screenshot_sha256',audited.get(ann['screenshot']))
        if expected_hash and hashlib.sha256((root/sample['screenshot']).read_bytes()).hexdigest()!=expected_hash:
            skipped.append({'screenshot':sample['screenshot'],'reason':'screenshot changed since landmark annotation'})
            continue
        reference = np.array([p['reference'] for p in ann['points']], float)
        screenshot = np.array([p['screenshot'] for p in ann['points']], float)
        gt, residual = fit_similarity(reference, screenshot)
        candidate = sample['candidates'][0]
        p = candidate['pose']
        pred = np.array([p['scale'], p['tx'], p['ty']])
        reprojection = pred[0]*reference+pred[1:]
        errors = np.linalg.norm(reprojection-screenshot, axis=1)
        expected_label_error = float(np.hypot(gt[0]*manual['reference_click_uncertainty_px'], manual['screenshot_click_uncertainty_px']))
        rows.append({'screenshot': sample['screenshot'], 'map_correct': candidate['map_id'] == sample['gt_map'],
                     'predicted_floor':candidate['floor'],'annotated_floor':ann['floor'],
                     'floor_correct':candidate['floor']==ann['floor'] and candidate['map_id']==sample['gt_map'],
                     'landmarks': len(reference), 'manual_fit': {'scale': gt[0], 'tx': gt[1], 'ty': gt[2]},
                     'manual_fit_rmse_px': float(np.sqrt(np.mean(residual**2))),
                     'manual_fit_max_error_px': float(residual.max()),
                     'expected_label_error_px': expected_label_error,
                     'scale_relative_error': float(abs(pred[0]-gt[0])/gt[0]),
                     'translation_l2_error_px': float(np.linalg.norm(pred[1:]-gt[1:])),
                     'reprojection_rmse_px': float(np.sqrt(np.mean(errors**2))),
                     'reprojection_max_error_px': float(errors.max()),
                     'point_errors': [{'name': a['name'], 'manual_fit_error_px': float(e), 'prediction_error_px': float(pe)} for a, e, pe in zip(ann['points'], residual, errors)]})
    valid = [r for r in rows if r['map_correct']]
    result = {'annotation_source': manual['source'], 'quality': manual['quality'],
              'annotations_sha256': hashlib.sha256(annotations_path.read_bytes()).hexdigest(),
              'prediction_source': str(predictions), 'skipped': skipped,
              'warning': 'Provisional manual labels include click uncertainty; translation is at full reference origin, not local anchor drift. Do not claim subpixel accuracy.',
              'metrics': {'samples': len(rows), 'identity_correct_samples': len(valid),
                          'floor_accuracy':sum(r['floor_correct'] for r in rows)/len(rows) if rows else None,
                          'landmark_count':sum(r['landmarks'] for r in rows),
                          'median_scale_relative_error': float(np.median([r['scale_relative_error'] for r in valid])) if valid else None,
                          'median_translation_l2_px': float(np.median([r['translation_l2_error_px'] for r in valid])) if valid else None,
                          'median_reprojection_rmse_px': float(np.median([r['reprojection_rmse_px'] for r in valid])) if valid else None,
                          'worst_reprojection_error_px': max((r['reprojection_max_error_px'] for r in valid), default=None)}, 'samples': rows}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictions', type=Path, default=Path('out/mapmatching/known_hard.json'))
    parser.add_argument('--output', type=Path, default=Path('out/mapmatching/pose_evaluation.json'))
    args = parser.parse_args()
    evaluate(Path(__file__).resolve().parents[2], args.predictions, args.output)
