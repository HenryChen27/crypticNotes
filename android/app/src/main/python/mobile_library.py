import json
from pathlib import Path

import cv2
from mapmatching.src import layout_library
from mapmatching.src.display_art import png_bytes, read_display_map
from mapmatching.src.map_update import child
from mobile_images import decode_art


def builtin_root(root):
    return Path(root)/'modules/notes'


def catalog(root, scene, difficulty):
    return json.dumps(layout_library.floor_catalog(builtin_root(root),scene,difficulty))


def preview(root,scene,difficulty,layout,layer):
    return layout_library.floor_art(builtin_root(root),scene,difficulty,layout,layer,decode_art)


def author_preview(root, source, max_dimension):
    path = child(Path(root)/'maps', Path(source).relative_to('maps'))
    image = read_display_map(path, decode_art)
    height, width = image.shape[:2]
    ratio = min(1., int(max_dimension)/max(width, height))
    if ratio < 1:
        image = cv2.resize(image, (max(1, round(width*ratio)), max(1, round(height*ratio))), interpolation=cv2.INTER_AREA)
    return png_bytes(image)
