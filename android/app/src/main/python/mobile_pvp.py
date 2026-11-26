"""Reads the hunter's banned survivors and the map from a ranked lobby frame.

The map is written in two places: "排位模式 - 地图" at the bottom right of the
lobby, and "前往【地图】" at the top left - there already while the survivors
ban the hunter's traits, before the lobby, and again while the match loads.

The lobby draws every name in one typeface (华康POP1体W5), so the names are not
recognised as text: each label is compared with the roster names rendered in
that typeface (mobile_pvp_templates, built by scripts/build_pvp_templates.py).
A general text recogniser read these small tilted labels wrong about one frame
in three; a closed set of known shapes does not have that problem.

Only numpy and OpenCV calls that exist in OpenCV 4.5.1 are used, so the same
file runs on the phone (Chaquopy) and on a desktop against saved frames.
"""
import json
from pathlib import Path

import cv2
import numpy as np

# Fractions of the frame HEIGHT: the lobby UI scales with height and hugs the corners.
BAN_ROI = (0.20, 0.155, 1.20, 0.245)        # x0, y0, x1, y1 from the left edge
MAP_ROI = (1.25, 0.795, 0.10, 0.87)         # x0 and x1 measured from the RIGHT edge
GOTO_ROI = (0.0, 0.04, 0.80, 0.17)          # the "前往【地图】" line, from the left edge
# A name label shows three characters at most (a longer name ends in ".."), so three are compared.
NAME_SHOWN = 3
NORMAL_HEIGHT = 32
NAME_SCORE, NAME_MARGIN = 0.60, 0.05
# Names this close to the winner get a second look at only the strokes that tell the two apart.
DUEL_WITHIN, DUEL_MARGIN = 0.25, 0.10
MAP_SCORE = 0.55

_templates = None
_directory = None


def configure(directory):
    global _directory, _templates
    _directory=Path(directory)
    _templates=None


def templates():
    global _templates
    if _templates is None:
        root = _directory
        if root is None:raise ValueError('请先安装 PVP 可选包')
        index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
        sheet = cv2.imdecode(np.frombuffer((root / 'sheet.png').read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        _templates = {'names': [], 'maps': [], 'prefix': None, 'goto': None}
        for entry in index['entries']:
            x, y, w, h = entry['box']
            mask = sheet[y:y + h, x:x + w]
            # Names are compared at the common height; the map lines are matched at screen scale instead.
            item = (entry['name'], entry['text'], _fit(_core(mask)) if entry['kind'] == 'name' else mask)
            if entry['kind'] in ('prefix', 'goto'):
                _templates[entry['kind']] = item[2]
            else:
                _templates[entry['kind'] + 's'].append(item)
    return _templates


def decode_raw(data, width, height, stride=0):
    stride = stride or width * 4
    pixels = np.frombuffer(bytes(data), np.uint8)
    rows = np.lib.stride_tricks.as_strided(pixels, (height, width, 4), (stride, 4, 1))
    return cv2.cvtColor(np.ascontiguousarray(rows), cv2.COLOR_RGBA2BGR)


def _crop(frame, roi, from_right=False):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = roi
    xa, xb = (w - int(x0 * h), w - int(x1 * h)) if from_right else (int(x0 * h), int(x1 * h))
    return frame[int(y0 * h):int(y1 * h), max(0, xa):min(w, xb)]


def _core(mask):
    """The characters themselves: small marks outside the first and last full-size stroke are dropped.

    On a label those are bits of the paper's border and shadow, plus the quote
    mark and the ".." of a shortened name; the templates go through the same
    step, so both sides lose the same things and only whole characters are compared.
    """
    count, labels, stats, centroids = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    if count <= 2:
        return mask
    heights, widths = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH]
    # Full-size strokes - or half of a character built of an upper and a lower part (the 日 and
    # 比 of 昆): lower than half a line, but as wide as a character. Quotes and dots are neither.
    tall = (heights >= 0.5 * heights.max()) | ((heights >= 0.35 * heights.max()) & (widths >= 0.6 * heights.max()))
    left = stats[1:, cv2.CC_STAT_LEFT][tall].min()
    right = (stats[1:, cv2.CC_STAT_LEFT] + stats[1:, cv2.CC_STAT_WIDTH])[tall].max()
    keep = np.zeros(count, bool)
    keep[1:] = tall | ((centroids[1:, 0] >= left) & (centroids[1:, 0] <= right))
    return np.where(keep[labels], mask, 0).astype(mask.dtype)


def _fit(mask, height=NORMAL_HEIGHT):
    """Ink mask cropped to its ink and scaled to a common height."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    mask = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    width = max(1, int(round(mask.shape[1] * height / mask.shape[0])))
    return cv2.resize(mask, (width, height), interpolation=cv2.INTER_AREA)


def _similarity(a, b):
    """Correlation of two same-height ink masks, forgiving a pixel or two of drift."""
    width = max(a.shape[1], b.shape[1])
    if min(a.shape[1], b.shape[1]) < 0.78 * width:
        return 0.0
    a = cv2.GaussianBlur(cv2.resize(a, (width, NORMAL_HEIGHT)).astype(np.float32), (0, 0), 1.2)
    b = cv2.GaussianBlur(cv2.resize(b, (width, NORMAL_HEIGHT)).astype(np.float32), (0, 0), 1.2)
    a -= a.mean(); b -= b.mean()
    denominator = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denominator) if denominator > 0 else 0.0


def _ink(strip):
    """Dark strokes lying on pale paper, away from the paper's own edges."""
    h = strip.shape[0]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    pale = (gray > 150).astype(np.uint8)
    # Close the strokes so a label is one solid piece of paper; the photos above
    # are far larger than a stroke and stay open.
    k = max(3, int(round(h * 0.16)) | 1)
    paper = cv2.morphologyEx(pale, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    # A label's border and drop shadow are dark too; step in from the edge to leave them out.
    e = max(3, int(round(h * 0.07)) | 1)
    paper = cv2.erode(paper, cv2.getStructuringElement(cv2.MORPH_RECT, (e, e)))
    return ((gray < 125) & (paper > 0)).astype(np.uint8)


def label_inks(strip):
    """Upright ink masks of the name labels in the ban strip, left to right, with their x position."""
    h = strip.shape[0]
    ink = _ink(strip)
    # Letters of one label sit closer together than labels do.
    joined = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(h * 0.20)) | 1, 3)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    found = []
    for i in range(1, count):
        x, y, w, hh, _ = stats[i]
        if hh < 0.15 * h or hh > 0.75 * h or w < 1.3 * hh or w > 3.0 * h:
            continue
        mask = _core(((labels == i) & (ink > 0)).astype(np.uint8) * 255)
        points = cv2.findNonZero(mask)
        if points is None or len(points) < 40:
            continue
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(points)
        # minAreaRect's angle convention changed between OpenCV versions; fold it into (-45, 45].
        if rw < rh:
            angle += 90
        while angle > 45:
            angle -= 90
        while angle <= -45:
            angle += 90
        turn = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        upright = cv2.warpAffine(mask, turn, (mask.shape[1], mask.shape[0]), flags=cv2.INTER_LINEAR)
        fitted = _fit((upright > 127).astype(np.uint8) * 255)
        if fitted is not None:
            found.append((int(x), fitted))
    return sorted(found, key=lambda item: item[0])


def read_bans(frame):
    """[(name, score)] for the labels that match a roster name, left to right."""
    return read_ban_strip(_crop(frame, BAN_ROI))


def _correlation(a, b):
    a = a - a.mean(); b = b - b.mean()
    denominator = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denominator) if denominator > 0 else 0.0


def _duel(ink, first, second):
    """Scores of two look-alike names (调香师 / 调酒师, 舞女 / 盲女) over the columns where they differ."""
    width = ink.shape[1]
    blurred = [cv2.GaussianBlur(cv2.resize(mask, (width, NORMAL_HEIGHT)).astype(np.float32), (0, 0), 1.2)
               for mask in (ink, first, second)]
    differs = np.abs(blurred[1] - blurred[2]).mean(axis=0)
    columns = differs > 0.5 * differs.max()
    if differs.max() <= 0 or columns.sum() < 3:
        return 0.0, 0.0
    return _correlation(blurred[0][:, columns], blurred[1][:, columns]), \
        _correlation(blurred[0][:, columns], blurred[2][:, columns])


def _leading(ink, width):
    """The left `width` columns of a fitted label: its first characters, fitted again."""
    return _fit(ink[:, :width])


def read_ban_strip(strip):
    out = []
    for _, ink in label_inks(strip):
        best = {}
        for name, text, template in templates()['names']:
            score = _similarity(ink, template)
            # A longer name the game did not cut to three characters: only its first three are
            # compared, which is all the template has. Characters are evenly spaced, so they are
            # the first 3/n of the label.
            full = len(name.strip('“”"'))
            if full > NAME_SHOWN and ink.shape[1] > 1.1 * template.shape[1]:
                head = _leading(ink, int(round(ink.shape[1] * NAME_SHOWN / full)))
                if head is not None:
                    score = max(score, _similarity(head, template))
            if score > best.get(name, (0.0, None))[0]:
                best[name] = (score, template)
        ranked = sorted(best.items(), key=lambda item: -item[1][0])
        if not ranked or ranked[0][1][0] < NAME_SCORE:
            continue
        name, (score, template) = ranked[0]
        if len(ranked) > 1 and score - ranked[1][1][0] < DUEL_WITHIN:
            rival, (_, rival_template) = ranked[1]
            mine, theirs = _duel(ink, template, rival_template)
            if abs(mine - theirs) < DUEL_MARGIN:
                continue                       # cannot tell: better no name than a wrong one
            if theirs > mine:
                name, score = rival, ranked[1][1][0]
        if name not in [found for found, _ in out]:
            out.append((name, round(score, 3)))
    return out


def read_map(frame):
    """(map, score) from the "排位模式 - 地图" line, or None when the line is not there."""
    return read_map_strip(_crop(frame, MAP_ROI, from_right=True))


def read_map_strip(strip):
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    return _line((gray > 165).astype(np.uint8) * 255, templates()['prefix'], np.arange(0.36, 0.60, 0.03) * strip.shape[0])


def read_goto(frame):
    """(map, score) from the "前往【地图】" line at the top left, or None."""
    return read_goto_strip(_crop(frame, GOTO_ROI))


def read_goto_strip(strip):
    # Pale letters on the dark corner of the screen; greyer while the match loads than in the ban stage.
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    floor = float(np.percentile(gray[::2, ::2], 50))
    if floor > 110:
        return None                             # no dark corner here: some other screen
    return _line((gray > max(120.0, floor + 55)).astype(np.uint8) * 255, templates()['goto'],
                 np.arange(0.15, 0.30, 0.012) * strip.shape[0])     # measured: 0.185 in the ban stage, 0.223 while loading


def _line(ink, prefix, heights):
    """A line of fixed words followed by a map name, in white-on-black `ink`: (map, score), or None.
    `heights`: how tall the fixed words may be drawn, in pixels."""
    best = None
    # The line's size follows the screen height; find it once with the fixed words.
    for height in heights:
        scale = height / prefix.shape[0]
        probe = cv2.resize(prefix, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if probe.shape[0] > ink.shape[0] or probe.shape[1] > ink.shape[1]:
            continue
        result = cv2.matchTemplate(ink, probe, cv2.TM_CCOEFF_NORMED)
        _, score, _, where = cv2.minMaxLoc(result)
        if best is None or score > best[0]:
            best = (score, scale, where, probe.shape)
    if best is None or best[0] < MAP_SCORE:
        return None
    _, scale, (px, py), (ph, pw) = best
    # The map name is what follows the fixed words on the same line.
    rest = ink[max(0, py - ph // 3):py + ph + ph // 3, px + pw:]
    winner = None
    for name, _, template in templates()['maps']:
        probe = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if probe.shape[0] > rest.shape[0] or probe.shape[1] > rest.shape[1]:
            continue
        _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(rest, probe, cv2.TM_CCOEFF_NORMED))
        if winner is None or score > winner[1]:
            winner = (name, score)
    if winner is None or winner[1] < MAP_SCORE:
        return None
    return winner[0], round(float(winner[1]), 3)


def read_strips(ban, ban_width, ban_height, area, area_width, area_height, goto=None, goto_width=0, goto_height=0):
    """Bridge entry. The phone cuts the regions itself (PvpBanText holds the same
    fractions as BAN_ROI / MAP_ROI / GOTO_ROI) and sends them as tight RGBA rows.
    `ban` and `area` are None while no ban card is up; `goto` is None when that corner shows no writing.
    Returns JSON {"bans": [...], "map": name or null, "scores": text for the log}."""
    bans = read_ban_strip(decode_raw(ban, ban_width, ban_height)) if ban is not None else []
    # The lobby's own map line is only worth looking for while the ban cards are up.
    found = read_map_strip(decode_raw(area, area_width, area_height)) if bans and area is not None else None
    if goto is not None:
        other = read_goto_strip(decode_raw(goto, goto_width, goto_height))
        if other is not None and (found is None or other[1] > found[1]):
            found = other
    return json.dumps({'bans': [name for name, _ in bans], 'map': found[0] if found else None,
                       'scores': ' '.join('%s=%.2f' % item for item in bans) + (' | %s=%.2f' % found if found else '')},
                      ensure_ascii=False)
