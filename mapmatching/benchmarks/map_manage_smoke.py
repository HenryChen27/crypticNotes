"""Real Qt map-management smoke; temporary maps/ tree only, no user settings modified.

覆盖：列表渲染与计数行、移除进「已停用」组、恢复、原图与特征原地不动、
删到最后一个的警告、过滤器、缩略图小窗、确认框不把宿主框一起带走。
产物截图在 out/mapmatching/map_manage/，用来肉眼核对版式。
"""
from pathlib import Path
import tempfile
import cv2
import numpy as np
from mapmatching.ui import W,C,STYLE,css_font,ARROW,font_stack,native
from mapmatching.theme import ChalkButton
from mapmatching.map_manage_ui import ConfirmDialog, MapManageDialog, MapRow, RowButton
from mapmatching.src import mapstore
from mapmatching.src.map_admin import list_maps
from mapmatching.src.map_library import add_map
from PySide6.QtTest import QTest

# 一张困难、三张噩梦单人 —— 困难只有一张，「最后一张」的警告才试得出来。
FIXTURE=[('北-T门','hard',None,30),('左 - 竖L门','nightmare','solo',60),
         ('自建甲','nightmare','solo',90),('自建乙','nightmare','solo',120)]


def register(root,name,difficulty,mode,marker):
    """同 test_map_library 验证过的几何；marker 只扰动哈希，避免撞 pixel_sha256。

    以前这里要合成一份假 index 再塞一张真图进 user_maps；现在所有图都走 add_map
    登记进同一棵 maps/ 树，索引由 add_map 自己增量建，夹具因此只剩这一步。
    """
    image=np.zeros((300,300,3),np.uint8)
    image[40:220,40:100]=120
    image[150:220,40:240]=120
    image[5:15,5:15]=marker
    source=root/f'{name}.png'
    cv2.imencode('.png',image)[1].tofile(source)
    regions=([dict(floor=1,bbox=[0,0,300,150]),dict(floor=2,bbox=[0,150,300,300])] if difficulty=='hard'
             else [dict(floor=-1,bbox=[0,0,300,240]),dict(floor=1,bbox=[0,150,300,300])])
    return add_map(root,source,name,difficulty,mode,regions)


def main():
    root=Path(__file__).resolve().parents[2]
    native.dpi_aware()
    app=W.QApplication([]); font_stack()
    app.setStyleSheet(STYLE.replace('__FONT__',css_font()).replace('__ARROW__',ARROW))
    with tempfile.TemporaryDirectory(prefix='map-manage-') as tmp:
        work=Path(tmp)
        maps=mapstore.maps_dir(work)
        for name,difficulty,mode,marker in FIXTURE:
            register(work,name,difficulty,mode,marker)
        assert len(list_maps(work))==4

        dialog=MapManageDialog(work,'nightmare','solo')
        dialog.show()
        for _ in range(3):
            app.processEvents()
        assert dialog.total==4 and dialog.active==4,dialog.summary.text()
        counts=lambda: dialog.summary.text()
        assert counts()=='共 4 张 · 可用 4 · 已停用 0',counts()
        out=root/'out/mapmatching/map_manage'; out.mkdir(parents=True,exist_ok=True)
        assert dialog.grab().save(str(out/'list.png'))
        # 按类而不是按 objectName 找行：选中的那一行 objectName 是 maprow-on。
        names=lambda: {w.findChild(W.QLabel,'mapname').text() for w in dialog.body.findChildren(MapRow)}
        assert names()=={'北-T门','左 - 竖L门','自建甲','自建乙'},names()

        def row(name):
            for widget in dialog.body.findChildren(MapRow):
                label=widget.findChild(W.QLabel,'mapname')
                if label is not None and label.text()==name:
                    return widget
            raise AssertionError(f'列表里没有这一行：{name}')

        def answer_confirm(confirm=True):
            box=app.activeModalWidget()
            assert isinstance(box,ConfirmDialog),box
            buttons=box.findChildren(ChalkButton)
            assert len(buttons)==2,buttons
            buttons[-1 if confirm else 0].click()

        def press(name,confirm=True):
            """点这一行的操作按钮，并回答弹出的确认框；返回确认框正文。"""
            captured={}
            def answer():
                box=app.activeModalWidget()
                assert isinstance(box,ConfirmDialog),box
                captured['body']=box.findChild(W.QLabel,'muted').text()
                answer_confirm(confirm)
            C.QTimer.singleShot(0,answer)
            QTest.mouseClick(row(name).findChild(RowButton),C.Qt.LeftButton)
            for _ in range(3):
                app.processEvents()
            assert 'body' in captured,'确认框没有弹出来'
            return captured['body']

        # 1) 移除一张：现在**只有软删除**（内置/自建之分已经没有了），所以总数不变、
        #    只是换到「已停用」组，可匹配数 -1。确认框必须写明可恢复。
        body=press('自建乙')
        assert '随时可以恢复' in body,body
        assert '无法撤销' not in body,'已经没有真删了，不该再出现不可撤销的说法'
        assert dialog.changed and dialog.total==4 and dialog.active==3,(dialog.total,dialog.active)
        assert counts()=='共 4 张 · 可用 3 · 已停用 1',counts()
        assert row('自建乙') is not None,'移除之后应当还在「已停用」组里'
        assert {r['name'] for r in list_maps(work)}=={'北-T门','左 - 竖L门','自建甲','自建乙'}

        # 2) 再移除一张：可匹配数继续 -1，而 load() 必须仍然不抛异常、也不含它。
        left=next(e for e in mapstore.read_manifest(maps) if e['name']=='左 - 竖L门')
        source_path=work/left['source']
        evidence=maps/'evidence'/mapstore.evidence_name(left['map_id'])
        assert source_path.exists() and evidence.exists()
        body=press('左 - 竖L门')
        assert '随时可以恢复' in body,body
        assert dialog.total==4 and dialog.active==2,(dialog.total,dialog.active)
        assert counts()=='共 4 张 · 可用 2 · 已停用 2',counts()
        ids=[r.map_id for r in mapstore.load_references(maps)]
        assert 'hard/北-T门' in ids and 'nightmare/solo/左 - 竖L门' not in ids,ids
        assert row('左 - 竖L门') is not None,'移除之后应当还在「已停用」组里'
        # 移除只是把登记条目搬进 disabled.json —— 原图和特征文件都原地不动。
        assert source_path.exists(),'原图不该被删'
        assert evidence.exists(),'特征文件不该被删'

        # 3) 恢复：回到可匹配集合里，disabled.json 只剩上一张。
        body=press('左 - 竖L门')
        assert '重新参与匹配' in body,body
        assert dialog.active==3,dialog.active
        assert counts()=='共 4 张 · 可用 3 · 已停用 1',counts()
        # 只断言成员关系，不按原顺序断言 —— 顺序本身有 `test_map_admin` 逐字节盯着，
        # 这里关心的是「回到可匹配集合里」。
        ids=[r.map_id for r in mapstore.load_references(maps)]
        assert 'nightmare/solo/左 - 竖L门' in ids and len(ids)==3,ids
        assert [e['map_id'] for e in mapstore.read_disabled(maps)]==['nightmare/solo/自建乙']
        assert source_path.exists() and evidence.exists()

        # 4) 某个难度只剩最后一张 —— 确认框必须点名警告（matcher.py:38 那条 raise 没有兜底）。
        body=press('北-T门',confirm=False)
        assert '最后一张可用地图' in body,body
        assert dialog.active==3,'取消了就不该有任何变化'
        assert not (maps/'.import.lock').exists(),'录入锁没清掉'

        # 5) 过滤器
        dialog.filter.setCurrentIndex(1)
        app.processEvents()
        assert names()=={'北-T门'},names()
        dialog.filter.setCurrentIndex(0)
        app.processEvents()
        assert len(dialog.body.findChildren(MapRow))==4
        assert dialog.grab().save(str(out/'list-after.png'))

        # 6) 缩略图：点行身弹小窗、再点一次收起、点别的行换图。
        #    这几张的 source 都是临时 maps/ 里真实存在的图，所以这里走真解码。
        area=W.QApplication.primaryScreen().availableGeometry()
        target=row('自建甲')
        QTest.mouseClick(target,C.Qt.LeftButton)
        for _ in range(3): app.processEvents()
        assert dialog.picked_id.endswith('自建甲'),dialog.picked_id
        assert dialog.popup.isVisible() and not dialog.popup.image.pixmap().isNull(),'缩略图没解出像素'
        assert target.objectName()=='maprow-on'
        assert area.contains(dialog.popup.geometry()),'缩略图小窗跑出屏幕了'
        assert dialog.popup.geometry().left()<dialog.geometry().left(),'小窗默认弹在框的左边'
        assert dialog.popup.image.pixmap().width()<=340,'缩略图应当按目标尺寸解码'
        assert dialog.grab().save(str(out/'list-thumbnail.png'))
        assert dialog.popup.grab().save(str(out/'thumbnail.png'))
        # 点同一行收起
        QTest.mouseClick(target,C.Qt.LeftButton)
        for _ in range(3): app.processEvents()
        assert not dialog.popup.isVisible() and dialog.picked_id is None
        # 缺原图时给占位文字而不是崩掉：把这张已停用地图的原图改名，模拟用户手动删了文件
        # （它已停用，不会再抽特征，改名不影响后面的断言）。
        orphan=next(e for e in mapstore.read_disabled(maps) if e['name']=='自建乙')
        Path(work/orphan['source']).rename(Path(work/orphan['source']).with_suffix('.bak'))
        QTest.mouseClick(row('自建乙'),C.Qt.LeftButton)
        for _ in range(3): app.processEvents()
        assert dialog.popup.isVisible() and dialog.popup.image.pixmap().isNull()
        assert '失败' in dialog.popup.image.text(),dialog.popup.image.text()
        # 点另一行换图
        QTest.mouseClick(row('自建甲'),C.Qt.LeftButton)
        for _ in range(3): app.processEvents()
        assert dialog.picked_id.endswith('自建甲') and dialog.popup.isVisible()
        assert dialog.isVisible(),'点行身之后管理框自己不该被关掉'

        # 7) 点框里别的地方 -> 收起缩略图，但框还开着
        QTest.mouseClick(dialog.filter,C.Qt.LeftButton,pos=C.QPoint(4,20))
        for _ in range(3): app.processEvents()
        assert not dialog.popup.isVisible(),'点到别处应当收起缩略图'
        assert dialog.isVisible(),'收起缩略图不该把整个框也关掉'

        # 8) 打开的确认框不能把宿主对话框一起带走（WindowDeactivate 的误伤）
        C.QTimer.singleShot(0,answer_confirm)
        QTest.mouseClick(row('自建甲').findChild(RowButton),C.Qt.LeftButton)
        for _ in range(3): app.processEvents()
        assert dialog.isVisible(),'确认框弹出把管理框一起关掉了'

        print('PASS: list and counts line, soft-remove into the disabled section with originals '
              'and features intact, restore, last-map warning, filter, thumbnail popup and '
              'confirm-dialog coexistence; screenshots in out/mapmatching/map_manage')


if __name__=='__main__':
    main()
