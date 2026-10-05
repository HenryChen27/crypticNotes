"""Tripwire for the home screen's fold bars.

A fold is two views: the bar you tap, and the body it hides. Built by hand they
are two `addView` calls, and dropping the bar's one leaves the bar unattached --
the section is simply not on screen. It compiles, lints clean, throws nothing;
the only symptom is that a player cannot find their settings. That happened
twice (both times the 游戏设置 fold vanished, taking the difficulty, opacity,
button size, map management and reset controls with it), so the shape of the
source is checked here instead of trusted.

Run from the repository root, no device needed:

    python android/tests/home_fold.py

What it pins down:

* The home screen builds fold bars in exactly one place, `MainActivity.fold`,
  and that one place attaches both halves. A half-built fold cannot exist.
* There is no second `heading(...)` call site in MainActivity for someone to
  hang a new section off without a bar.

This is a source check, not a UI test. It cannot see the rendered screen, and
passing it does not mean the screen was looked at.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / 'android/app/src/main/java/com/crypticnotes/mobile/MainActivity.java'
source = SRC.read_text(encoding='utf-8')
failures = []


def method_body(text, signature):
    """The balanced {...} that follows the first occurrence of `signature`."""
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[opening:index + 1]
    raise SystemExit('unbalanced braces after: ' + signature)


if 'private LinearLayout fold(' not in source:
    print('FAIL: MainActivity has no fold(); a fold bar built anywhere else is not attached')
    sys.exit(1)

fold = method_body(source, 'private LinearLayout fold(')
for needed in ('content.addView(bar)', 'content.addView(body)'):
    if needed not in fold:
        failures.append('MainActivity.fold leaves the fold half-built: no `%s`' % needed)

# `private Theme.SectionHeading heading(String label)` is the declaration, not a
# call; everything else is a fold bar somebody has to attach.
calls = []
for match in re.finditer(r'\bheading\(', source):
    window = source[max(0, match.start() - 30):match.start() + 32]
    if 'SectionHeading heading(' in window:
        continue
    calls.append(match.start())

fold_start = source.index('private LinearLayout fold(')
fold_end = fold_start + len(fold)
for call in calls:
    if not fold_start <= call < fold_end:
        line = source.count('\n', 0, call) + 1
        failures.append('MainActivity.java:%d makes a fold bar outside fold(), where nothing '
                        'guarantees it gets added to a parent' % line)
if len(calls) != 1:
    failures.append('expected exactly one fold-bar call site (inside fold), found %d' % len(calls))

if failures:
    for failure in failures:
        print('FAIL:', failure)
    sys.exit(1)
print('OK: the home screen builds every fold bar in fold(), which attaches both halves')
