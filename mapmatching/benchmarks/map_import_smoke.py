"""Real Qt enrollment smoke; temporary maps/ tree only, no user settings modified."""
from pathlib import Path
import tempfile
import cv2
import numpy as np
from mapmatching.ui import W,C,G,STYLE,css_font,ARROW,font_stack,native
from mapmatching.map_import_ui import MapImportDialog
from mapmatching.src import mapstore
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.reference import read_image
from mapmatching.src.live import presentation_candidate,raw_layer
from PySide6.QtTest import QTest


def main():
    root=Path(__file__).resolve().parents[2]
    native.dpi_aware()
    app=W.QApplication([]); font_stack()
    app.setStyleSheet(STYLE.replace('__FONT__',css_font()).replace('__ARROW__',ARROW))
    # 拿一张真实噩梦单人图当录入素材：原图、楼层几何都从登记表读，不再有 floor_regions.json。
    entry=next(e for e in mapstore.read_manifest(mapstore.maps_dir(root)) if e['map_id'].startswith('nightmare/solo'))
    with tempfile.TemporaryDirectory(prefix='map-enrollment-') as tmp:
        tmp_maps=mapstore.maps_dir(Path(tmp))       # 只录入这一张，build_index 也就只碰这一张
        dialog=MapImportDialog(Path(tmp),'nightmare','solo')
        dialog.path=root/entry['source']; dialog.canvas.pixmap=G.QPixmap(str(dialog.path))
        dialog.name.setText('噩梦新地图 · 录入预览')
        dialog.show(); app.processEvents()
        canvas=dialog.canvas
        center=canvas.image_rect().center()
        anchor=canvas.point(center)
        canvas.zoom_at(center,3)
        assert (canvas.point(center)-anchor).manhattanLength()<.01
        before_pan=C.QPointF(canvas.pan)
        QTest.mouseClick(dialog.floor,C.Qt.LeftButton,pos=C.QPoint(dialog.floor.width()//2,20))
        assert dialog.floor.currentData()==2
        QTest.keyPress(dialog.floor,C.Qt.Key_Space)
        assert dialog.floor.currentData()==2 and canvas.space
        QTest.mousePress(canvas,C.Qt.LeftButton,pos=center.toPoint())
        QTest.mouseMove(canvas,(center+C.QPointF(60,35)).toPoint())
        QTest.mouseRelease(canvas,C.Qt.LeftButton,pos=(center+C.QPointF(60,35)).toPoint())
        QTest.keyRelease(canvas,C.Qt.Key_Space)
        assert dialog.floor.currentData()==2 and not canvas.space
        dialog.floor.setCurrentIndex(0)
        assert not canvas.boxes and (canvas.pan-before_pan).manhattanLength()>80
        canvas.fit()
        assert canvas.zoom==1 and canvas.pan.isNull()
        r=dialog.canvas.image_rect()
        QTest.mousePress(dialog.canvas,C.Qt.LeftButton,pos=(r.topLeft()+C.QPointF(8,8)).toPoint())
        QTest.mouseMove(dialog.canvas,(r.topLeft()+C.QPointF(60,70)).toPoint())
        QTest.mouseRelease(dialog.canvas,C.Qt.LeftButton,pos=(r.topLeft()+C.QPointF(60,70)).toPoint())
        assert 1 in dialog.canvas.boxes
        dialog.clear(); assert not dialog.canvas.boxes
        dialog.canvas.boxes={r['floor']:r['bbox'] for r in entry['regions']}
        dialog.summary(); dialog.canvas.update(); app.processEvents()
        out=root/'out/mapmatching/map_import'; out.mkdir(parents=True,exist_ok=True)
        assert dialog.grab().save(str(out/'dialog.png'))
        C.QTimer.singleShot(100,dialog.save_map)
        C.QTimer.singleShot(20000,app.quit)
        app.exec()
        assert dialog.result_record is not None,dialog.status.text()
        # add_map 只登记条目；索引得显式建一次，load_references 才认（它逐条校验 entry_sha）。
        mapstore.build_index(tmp_maps)
        refs=mapstore.load_references(tmp_maps,difficulty='nightmare',mode='solo')
        assert len(refs)==1 and len(refs[0].regions)==3
        matcher=MapMatcher(tmp_maps,difficulty='nightmare',mode='solo')
        ref=refs[0]; original=read_image(Path(tmp)/ref.source)
        x,y,X,Y=next(r['bbox'] for r in ref.regions if r['floor']==1)
        scale=min(1000/(X-x),530/(Y-y))
        matrix=np.array([[scale,0,1100-scale*(x+X)/2],[0,scale,540-scale*(y+Y)/2]])
        source=np.zeros_like(original); source[y:Y,x:X]=original[y:Y,x:X]
        screen=cv2.warpAffine(source,matrix,(1920,1080))
        candidate,message=presentation_candidate(matcher.match(screen))
        assert candidate is not None and candidate.map_id==ref.map_id and candidate.floor==1,message
        assert raw_layer(screen.shape,original,ref,candidate)[:,:,3].any()
        print('PASS: cursor-anchored zoom, Space pan without annotation, fit, source-pixel drag, async import and recognition/overlay')


if __name__=='__main__':
    main()
