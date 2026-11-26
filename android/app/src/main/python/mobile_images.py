"""Reference image decoding with Android codec fallback for WebP-less OpenCV."""
from pathlib import Path
import cv2
import numpy as np


def _android_png(path=None, data=None):
    # The Android OpenCV wheel may omit libwebp. Use the OS decoder only on
    # that path; references are cached by mobile_bridge, not decoded per frame.
    from java import jclass
    BitmapFactory = jclass('android.graphics.BitmapFactory')
    CompressFormat = jclass('android.graphics.Bitmap$CompressFormat')
    OutputStream = jclass('java.io.ByteArrayOutputStream')
    bitmap = BitmapFactory.decodeFile(str(path)) if data is None else BitmapFactory.decodeByteArray(data,0,len(data))
    if bitmap is None:
        raise ValueError(f'Android cannot decode image: {path}')
    stream = OutputStream()
    try:
        if not bitmap.compress(CompressFormat.PNG, 100, stream):
            raise ValueError(f'Android image conversion failed: {path}')
        return bytes(stream.toByteArray())
    finally:
        stream.close()
        bitmap.recycle()


def read_image(path):
    path = Path(path)
    data = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is not None:
        return image
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        image = cv2.imdecode(np.frombuffer(_android_png(path), np.uint8), cv2.IMREAD_COLOR)
        if image is not None:
            return image
    raise ValueError(f'Cannot decode image: {path}')


def decode_art(data, flags=cv2.IMREAD_UNCHANGED):
    image = cv2.imdecode(data,flags)
    if image is None:
        image = cv2.imdecode(np.frombuffer(_android_png(data=data.tobytes()),np.uint8),flags)
    return image
