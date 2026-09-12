"""Measure fresh process wall time, including imports, loading and decoding."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import time
import argparse
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--difficulty', choices=['hard', 'nightmare'], required=True)
    parser.add_argument('--mode', choices=['solo', 'duo'])
    parser.add_argument('--samples', type=Path, default=Path('out/mapmatching/known_hard.json'))
    parser.add_argument('--output', type=Path, default=Path('out/mapmatching/cold_known_hard.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = root/'out/mapmatching'
    baseline = json.loads(args.samples.read_text(encoding='utf-8'))
    rows = []
    for i, sample in enumerate(baseline['samples']):
        start = time.perf_counter()
        command = [sys.executable, '-m', 'mapmatching', 'match', sample['screenshot'], '--difficulty', args.difficulty, '--output', str(output/f'cold_result_{i}.json')]
        if args.mode:
            command += ['--mode', args.mode]
        result = subprocess.run(command,
                                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr)
        rows.append({'screenshot': sample['screenshot'], 'milliseconds': (time.perf_counter()-start)*1000})
    data = {'definition': 'fresh Python process: imports + index load + image decode + inference + JSON serialization + process exit; OS file cache is not cleared', 'n': len(rows), 'median_ms': float(np.median([r['milliseconds'] for r in rows])), 'p95_ms': float(np.percentile([r['milliseconds'] for r in rows], 95)), 'samples': rows}
    args.output.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
