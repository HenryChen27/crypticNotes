"""Fresh benchmark. Labels are read here only, never in inference modules."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time
import cv2
import numpy as np
from mapmatching.src.evidence import extract
from mapmatching.src.reference import build, load, read_image
from mapmatching.src.retrieval import retrieve
from mapmatching.src.registration import register
from mapmatching.config import fingerprint


def evaluate(root: Path, index: Path, output: Path, *, spatial: bool = True, hud: bool = True, clean: bool = True,
             difficulty: str | None = None, mode: str | None = None) -> dict:
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    np.random.seed(0)
    begin = time.perf_counter()
    refs = load(index, difficulty=difficulty, mode=mode)
    if not refs:
        raise ValueError('No references for explicit session context')
    load_ms = (time.perf_counter()-begin)*1000
    metadata = json.loads((index/'index.json').read_text(encoding='utf-8'))
    if metadata['remove_annotations'] != clean:
        raise ValueError('Reference index preprocessing must match --no-clean; rebuild a separate index')
    hashes = {r['sha256']: r['map_id'] for r in metadata['references']}
    samples, skipped = [], []
    eligible_ids = {r.map_id for r in refs}
    # Pairing is evaluation-only, by exact original reference file hash.
    for directory in sorted((root/'examples').iterdir()):
        if not directory.is_dir():
            continue
        labelled, screenshots = [], []
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                continue
            identity = hashes.get(hashlib.sha256(path.read_bytes()).hexdigest())
            (labelled if identity else screenshots).append((path, identity))
        if not labelled:
            skipped.append({'example_directory': directory.relative_to(root).as_posix(),
                            'reason': 'no exact paired reference; cannot score identity accuracy'})
            continue
        if len(labelled) != 1:
            raise ValueError(f'Expected one exact paired reference in {directory}')
        if labelled[0][1] not in eligible_ids:
            skipped.append({'example_directory': directory.relative_to(root).as_posix(), 'reason': 'evaluation sample outside explicit context'})
            continue
        for path, _ in screenshots:
            pixels = read_image(path)
            start = time.perf_counter()
            ev = extract(pixels, exclude_hud=hud, remove_annotations=clean)
            extracted = time.perf_counter()
            ranking = retrieve(ev, refs, spatial=spatial)
            retrieved = time.perf_counter()
            candidates = [register(ev, item) for item in ranking[:5]]
            final = sorted(candidates, key=lambda c: -(c.explained or 0))
            end = time.perf_counter()
            gt = labelled[0][1]
            rank = next(i+1 for i, item in enumerate(ranking) if item.reference.map_id == gt)
            oracle_start = time.perf_counter()
            oracle = register(ev, ranking[rank-1])
            oracle_ms = (time.perf_counter()-oracle_start)*1000
            samples.append({'screenshot': path.relative_to(root).as_posix(), 'gt_map': gt, 'gt_source': 'user-provided paired reference exact SHA256', 'retrieval_rank': rank, 'retrieval': [{'map_id': v.reference.map_id, 'score': v.score, 'matches': v.matches} for v in ranking], 'candidates': [asdict(c) for c in final], 'oracle_registration_diagnostic_only': asdict(oracle), 'oracle_ms_excluded_from_inference': oracle_ms, 'evidence': ev.diagnostics, 'status': 'UNKNOWN', 'reason': 'research baseline: floor and confidence not validated', 'timing_ms': {'extraction': (extracted-start)*1000, 'retrieval': (retrieved-extracted)*1000, 'registration': (end-retrieved)*1000, 'total': (end-start)*1000}})
            debug = output.parent/'evidence'
            debug.mkdir(parents=True, exist_ok=True)
            cv2.imencode('.png', ev.mask*255)[1].tofile(debug/f'{directory.name}_mask.png')
            print(f'{directory.name}: rank={rank}, anchors={len(ev.corners)}, total_ms={(end-start)*1000:.1f}', flush=True)
    n = len(samples)
    metrics = {f'top{k}': sum(s['retrieval_rank']<=k for s in samples)/n if n else None for k in (1, 3, 5)}
    metrics.update({'n': n, 'candidate_count': len(refs), 'unique_gt_maps': len(set(s['gt_map'] for s in samples)), 'registered_top1': sum(bool(s['candidates']) and s['candidates'][0]['map_id']==s['gt_map'] for s in samples)/n if n else None, 'floor_accuracy': None, 'scale_error': None, 'translation_error': None, 'full_pose_error': None, 'unknown_rate': 1. if n else None, 'wrong_lock_rate': 0. if n else None, 'accepted_samples': 0, 'warm_median_ms': float(np.median([s['timing_ms']['total'] for s in samples])) if n else None, 'warm_p95_ms': float(np.percentile([s['timing_ms']['total'] for s in samples],95)) if n else None, 'index_load_ms': load_ms, 'cold_start_ms': None})
    result = {'status': 'EXPERIMENTAL_BASELINE', 'settings': {'spatial': spatial, 'hud': hud, 'clean': clean, 'seed': 0, 'threads': 1, 'top_k_registration': 5, 'config_fingerprint': fingerprint(), 'index_version': metadata['version'], 'difficulty': difficulty, 'mode': mode, 'context_source': 'explicit command-line input, never inferred by matcher'}, 'environment': {'python': platform.python_version(), 'opencv': cv2.__version__, 'numpy': np.__version__, 'platform': platform.platform()}, 'metrics': metrics, 'samples': samples, 'skipped': skipped, 'limitations': ['Development set only; four distinct Hard maps', 'No independent pose/floor ground truth', 'All decisions UNKNOWN by design; wrong-lock=0 is not proof of a useful classifier', 'Runtime excludes image decoding, includes evidence/retrieval/registration; not cold start', 'ROI uses a layout prior, not general UI detection']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--index', type=Path, default=Path('maps'))
    parser.add_argument('--output', type=Path, default=Path('out/mapmatching/baseline.json'))
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--no-spatial', action='store_true')
    parser.add_argument('--no-hud', action='store_true')
    parser.add_argument('--no-clean', action='store_true')
    parser.add_argument('--difficulty', choices=['hard', 'nightmare'])
    parser.add_argument('--mode', choices=['solo', 'duo'])
    args = parser.parse_args()
    if args.build:
        build(args.root, args.index, remove_annotations=not args.no_clean)
    report = evaluate(args.root, args.index, args.output, spatial=not args.no_spatial, hud=not args.no_hud, clean=not args.no_clean, difficulty=args.difficulty, mode=args.mode)
    print(json.dumps(report['metrics'], indent=2))
