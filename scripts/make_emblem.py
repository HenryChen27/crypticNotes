"""Turn the supplied white-on-black emblem into the floating button's icon.

The source is a white mark on a solid black field. Luminance becomes alpha and
every opaque pixel becomes white, so the anti-aliased edges stay smooth and the
black background drops out entirely -- which is what "只有白色部分" asks for.

Regenerate after replacing the source:

    python scripts/make_emblem.py

Writes android/app/src/main/res/drawable-nodpi/floating_emblem.png.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/assets/emblem-source.png'
TARGET = ROOT / 'android/app/src/main/res/drawable-nodpi/floating_emblem.png'
# Room around the mark so a circular crop never clips the outer curls.
MARGIN = .10
# Below this the source is sensor noise rather than ink; without it the trim
# box would grow to the whole frame chasing stray grey pixels.
FLOOR = 8


def main():
    source = Image.open(SOURCE).convert('L')
    width, height = source.size
    alpha = source.point(lambda v: 0 if v < FLOOR else v)

    box = alpha.getbbox()
    if box is None:
        raise SystemExit(f'{SOURCE} has no mark above the noise floor')
    alpha = alpha.crop(box)

    # Square it, so the drawable's aspect ratio cannot squash the mark.
    side = max(alpha.size)
    pad = round(side * MARGIN)
    canvas = Image.new('L', (side + pad * 2, side + pad * 2), 0)
    canvas.paste(alpha, ((canvas.width - alpha.width) // 2,
                         (canvas.height - alpha.height) // 2))

    mark = Image.new('RGBA', canvas.size, (255, 255, 255, 0))
    mark.putalpha(canvas)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    mark.save(TARGET)

    opaque = sum(1 for v in canvas.tobytes() if v)
    print(f'{SOURCE.name} {width}x{height} -> {TARGET.name} {mark.width}x{mark.height}')
    print(f'  trimmed box {box}, {opaque} opaque px '
          f'({opaque / (canvas.width * canvas.height):.1%} of the tile)')


if __name__ == '__main__':
    main()
