"""Export the in-app doll animation as vertical MP4 editing assets."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from mapmatching.appearance.player import PetAnimation


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "doll-short-video"
FPS = 40
SIZE = (1080, 1920)
FONT_FAMILY = "Microsoft YaHei UI"

ACTIONS = [
    ("idle", "01-待机呼吸", "待机中，也要认真呼吸", 4.0),
    ("curious", "02-随机挥手", "嗨！这次是哪只手呢？", 2.2),
    ("happy", "03-撒娇比心", "识别成功！夸夸我嘛", 3.6),
    ("puzzled", "04-挠头疑惑", "嗯……让我再看看", 2.2),
    ("angry", "05-着急生气", "怎么会有两张这么像！", 2.2),
    ("sleep", "06-困倦打盹", "没有新消息，我先眯一下", 2.2),
]


class DollCanvas(W.QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(112, 132)
        self.setAttribute(C.Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent")
        self.animation = PetAnimation(self)
        self.animation.enable(True)
        self.progress = 0.0

    def paintEvent(self, event):
        self.animation.paint(self.progress)


def qimage_array(image: G.QImage) -> np.ndarray:
    image = image.convertToFormat(G.QImage.Format_RGBA8888)
    view = np.frombuffer(image.bits(), np.uint8)
    return view.reshape(image.height(), image.bytesPerLine() // 4, 4)[:, : image.width()].copy()


def doll_frame(widget: DollCanvas, mood: str, progress: float) -> np.ndarray:
    widget.animation.mood = mood
    widget.animation.wave_right = mood == "curious" and progress >= 0.5
    widget.progress = progress
    image = G.QImage(widget.size(), G.QImage.Format_RGBA8888)
    image.fill(C.Qt.transparent)
    widget.render(image)
    return qimage_array(image)


def background() -> G.QImage:
    w, h = SIZE
    image = G.QImage(w, h, G.QImage.Format_RGBA8888)
    image.fill(G.QColor("#00ff00"))
    return image


def compose(base: G.QImage, doll: np.ndarray, title: str, subtitle: str) -> np.ndarray:
    frame = base.copy()
    painter = G.QPainter(frame)
    painter.setRenderHint(G.QPainter.SmoothPixmapTransform)
    qdoll = G.QImage(doll.data, doll.shape[1], doll.shape[0], doll.strides[0], G.QImage.Format_RGBA8888)
    target = C.QRect(176, 531, 728, 858)
    painter.drawImage(target, qdoll)
    painter.end()
    rgba = qimage_array(frame)
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


def writer(path: Path) -> cv2.VideoWriter:
    result = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SIZE)
    if not result.isOpened():
        raise RuntimeError("OpenCV cannot create MP4; install an MP4-capable codec")
    return result


def export_clip(widget: DollCanvas, base: G.QImage, item) -> Path:
    mood, stem, subtitle, seconds = item
    path = OUT / f"{stem}.mp4"
    video = writer(path)
    try:
        count = round(seconds * FPS)
        for index in range(count):
            progress = index / max(1, count - 1)
            video.write(compose(base, doll_frame(widget, mood, progress), stem[3:], subtitle))
    finally:
        video.release()
    return path


def main():
    global FONT_FAMILY
    OUT.mkdir(parents=True, exist_ok=True)
    app = W.QApplication.instance() or W.QApplication([])
    font_id = G.QFontDatabase.addApplicationFont(str(ROOT / "mapmatching" / "assets" / "fonts" / "HYDiWRGJ.ttf"))
    families = G.QFontDatabase.applicationFontFamilies(font_id)
    if families:
        FONT_FAMILY = families[0]
    widget = DollCanvas()
    base = background()
    clips = [export_clip(widget, base, item) for item in ACTIONS]

    reel = writer(OUT / "布偶全动作_竖版预览.mp4")
    try:
        for clip in clips:
            source = cv2.VideoCapture(str(clip))
            while True:
                ok, frame = source.read()
                if not ok:
                    break
                reel.write(frame)
            source.release()
    finally:
        reel.release()
    print("Exported:")
    for path in [*clips, OUT / "布偶全动作_竖版预览.mp4"]:
        print(f"  {path.relative_to(ROOT)} ({path.stat().st_size / 1024**2:.1f} MiB)")
    app.quit()


if __name__ == "__main__":
    main()
