from __future__ import annotations
import argparse
import json
from pathlib import Path
import cv2
from .src.matcher import MapMatcher
from .src.reference import build, read_image
from .src.context import SessionContext
from .src.preview import render_preview

# `maps/` 现在既是原图库也是索引目录，所以 --index 的默认值就是它。
# 参数名保留 `index`（含义仍是「参考图库所在目录」），免得改十几处调用点。
DEFAULT_MAPS = Path(__file__).resolve().parents[1]/'maps'


def main() -> None:
    parser = argparse.ArgumentParser(description='Map Matching v2 research CLI; no screen capture or game integration')
    commands = parser.add_subparsers(dest='command', required=True)
    index = commands.add_parser('build-index')
    index.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    index.add_argument('--index', type=Path, default=DEFAULT_MAPS)
    match = commands.add_parser('match')
    match.add_argument('screenshot', type=Path)
    match.add_argument('--index', type=Path, default=DEFAULT_MAPS)
    match.add_argument('--difficulty', choices=['hard', 'nightmare'], required=True)
    match.add_argument('--mode', choices=['solo', 'duo'])
    match.add_argument('--output', type=Path)
    preview = commands.add_parser('preview', help='Explicit offline candidate overlay; does not approve a lock')
    preview.add_argument('screenshot', type=Path)
    preview.add_argument('--difficulty', choices=['hard','nightmare'], required=True)
    preview.add_argument('--mode', choices=['solo','duo'])
    preview.add_argument('--index', type=Path, default=DEFAULT_MAPS)
    preview.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    preview.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    if args.command == 'build-index':
        build(args.index.resolve())
        print('Reference index built')
        return
    try:
        SessionContext(args.difficulty, args.mode)
    except ValueError as error:
        parser.error(str(error))
    matcher = MapMatcher(args.index, difficulty=args.difficulty, mode=args.mode)
    pixels = read_image(args.screenshot)
    matched = matcher.match(pixels)
    if args.command == 'preview':
        if not matched.candidates:
            parser.error('Insufficient evidence for a candidate preview')
        candidate = matched.candidates[0]
        reference = next(r for r in matcher.references if r.map_id == candidate.map_id)
        if args.output.resolve() in (args.screenshot.resolve(), (args.root/reference.source).resolve()):
            parser.error('Preview output must not overwrite an original image')
        if args.output.suffix.lower() not in ('.png','.jpg','.jpeg'):
            parser.error('Preview output must be PNG or JPEG')
        try:
            overlay, metadata = render_preview(pixels, read_image(args.root/reference.source), reference, candidate)
        except ValueError as error:
            parser.error(str(error))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imencode(args.output.suffix, overlay)[1].tofile(args.output)
        args.output.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(metadata,ensure_ascii=True,indent=2))
        return
    result = matched.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
