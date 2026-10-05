"""Contract check for the Android bridge: gate, registration, and `gated=`.

Run after `python scripts/prepare_android.py`, from the repository root:

    python android/tests/bridge_contract.py

Uses the six frames in `out/android-samples` (three with the map panel closed,
three open). No device or emulator needed -- this exercises the Python half of
the client only; the Java capture loop still needs on-device confirmation.

What it pins down:

* The three closed frames are refused and the three open ones pass the
  map-panel gate. This is a small sample, not a coverage claim.
* `mobile_bridge.match(data, output, gated=True)` -- the hot path, where Java
  has already run the gate on these exact frame bytes -- reaches the *same*
  verdict as `gated=False` on every frame the gate accepts. If a future edit
  makes the shortcut diverge, the client would register frames the gate would
  have rejected, so this is the assertion that matters.
* The warm-cache re-registration cost, which is what the overlay-follow latency
  after you stop panning is actually made of.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'android/app/src/main/python'))
sys.path.insert(0, str(ROOT))

import mobile_bridge  # noqa: E402  (path set up above)

ASSETS = ROOT / 'android/generated/assets'
SAMPLES = ROOT / 'out/android-samples'
CLOSED = ['closed-0', 'closed-1', 'closed-2']
OPEN = ['open-0', 'open-1', 'open-2']


def verdict(payload):
    """The answer, minus the non-deterministic timing counters."""
    details = dict(payload.get('details') or {})
    diagnostics = dict(details.get('diagnostics') or {})
    diagnostics.pop('timing_ms', None)
    diagnostics.pop('pipeline_ms', None)
    if diagnostics:
        details['diagnostics'] = diagnostics
    elif 'diagnostics' in details:
        details.pop('diagnostics')
    return {k: v for k, v in payload.items() if k != 'details'} | {'details': details}


def run(data, output, gated, reset=True):
    """`reset` clears the cache so the call does a real search; leaving it set
    reproduces the second call in a session, where the same map is still open."""
    if reset:
        mobile_bridge._cached = None
    started = time.perf_counter()
    result = json.loads(mobile_bridge.match(data, str(output), gated))
    return result, (time.perf_counter() - started) * 1000


def main():
    if not ASSETS.exists():
        raise SystemExit(f'{ASSETS} missing -- run scripts/prepare_android.py first')
    if not SAMPLES.exists():
        raise SystemExit(f'{SAMPLES} missing -- the sample frames are required')

    print('references:', mobile_bridge.initialize(str(ASSETS), 'hard', 'solo'))
    failures = []

    for name in CLOSED + OPEN:
        data = (SAMPLES / f'{name}.jpg').read_bytes()
        output = Path(tempfile.gettempdir()) / f'bridge-{name}.png'

        started = time.perf_counter()
        gate = json.loads(mobile_bridge.inspect(data))
        gate_ms = (time.perf_counter() - started) * 1000

        plain, plain_ms = run(data, output, gated=False)
        should_open = name in OPEN

        if gate['visible'] != should_open:
            failures.append(f'{name}: gate said visible={gate["visible"]}')
        if not should_open:
            # A frame the caller's own gate rejects never reaches match(gated=True).
            if plain['ok'] is not False:
                failures.append(f'{name}: closed frame was registered anyway')
            print(f'{name:9s} gate=NO  {gate_ms:5.0f}ms  refused: {plain["message"]}')
            continue

        hot, hot_ms = run(data, output, gated=True)
        if verdict(plain) != verdict(hot):
            failures.append(f'{name}: gated=True diverged from gated=False')

        size = output.stat().st_size if output.exists() else 0
        print(f'{name:9s} gate=yes {gate_ms:5.0f}ms  ok={plain["ok"]!s:5s} '
              f'name={plain.get("name", "-")} floor={plain.get("floor", "-")} layer={size}B')
        warm = f'{run(data, output, gated=True, reset=False)[1]:4.0f}ms' if hot['ok'] else 'n/a'
        print(f'          cold gated=False {plain_ms:4.0f}ms | cold gated=True {hot_ms:4.0f}ms '
              f'| warm re-registration {warm}')
        if not plain['ok']:
            print(f'          -> {plain["message"]} (abstention, not a bridge fault)')

    if failures:
        raise SystemExit('FAIL:\n  ' + '\n  '.join(failures))
    print('OK: gate verdicts as expected; the gated= shortcut agrees everywhere '
          'the gate accepts')


if __name__ == '__main__':
    main()
