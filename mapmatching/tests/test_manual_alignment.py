import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from dataclasses import replace
from mapmatching.src.types import Candidate, Pose
from mapmatching.src.manual_alignment import reliable_memory, blank_floor_offer, cross_floor_candidate
from mapmatching.src.live import ToggleState


class ManualAlignmentTests(unittest.TestCase):
    def setUp(self):
        trace_patch=patch('mapmatching.ui.trace')
        trace_patch.start();self.addCleanup(trace_patch.stop)
        self.confirmed=Candidate('nightmare/solo/example','nightmare','solo',8,Pose(1,0,0),.9,.1,1)

    def offer(self, floor=2, visible=True, confirmed=True):
        with patch('mapmatching.src.manual_alignment.manual_floor_reading',return_value={'floor':floor}), \
             patch('mapmatching.src.map_visibility.inspect_map_ui',return_value={'visible':visible}):
            return blank_floor_offer(object(),self.confirmed if confirmed else None,{})

    def test_only_confirmed_other_floor_visible_panel_offers_including_blank(self):
        self.assertEqual(self.offer()['floor'],2)
        for options in ({'floor':1},{'floor':None},{'visible':False},{'confirmed':False}):
            self.assertIsNone(self.offer(**options))
        self.confirmed=replace(self.confirmed,floor=2)
        self.assertEqual(self.offer(floor=1)['floor'],1)

    def test_manual_result_never_becomes_reliable_memory(self):
        self.assertTrue(reliable_memory(self.confirmed,{}))
        self.assertFalse(reliable_memory(self.confirmed,{'diagnostics':{'manual_alignment':True}}))
        self.assertTrue(reliable_memory(replace(self.confirmed,explained=.68,contradiction=.24),{}))
        self.assertFalse(reliable_memory(replace(self.confirmed,retrieval_score=2),{}))

    def test_cross_floor_auto_rejects_sparse_shrunken_and_ambiguous_fits(self):
        from mapmatching.src.manual_alignment import automatic_cross_floor_reliable
        from mapmatching.src.matcher import MatchResult
        good=replace(self.confirmed,floor=2)
        self.assertTrue(automatic_cross_floor_reliable(good,self.confirmed,MatchResult(candidates=[good])))
        for weak in (replace(good,retrieval_score=2),replace(good,pose=Pose(.15,0,0))):
            self.assertFalse(automatic_cross_floor_reliable(weak,self.confirmed,MatchResult(candidates=[weak])))
        rival=replace(good,map_id='other',explained=.88)
        self.assertFalse(automatic_cross_floor_reliable(good,self.confirmed,MatchResult(candidates=[good,rival])))

    def test_dark_floor_retry_requires_agreement_and_keeps_conflicts_rejected(self):
        import numpy as np
        from mapmatching.src.manual_alignment import manual_floor_reading
        image=np.zeros((10,20,3),np.uint8)
        with patch('mapmatching.src.floor_tabs.inspect_floor_tabs',side_effect=[
            {'floor':None,'reason':'tabs_not_clear'},{'floor':2},{'floor':2}]):
            self.assertEqual(manual_floor_reading(image)['floor'],2)
        with patch('mapmatching.src.floor_tabs.inspect_floor_tabs',side_effect=[
            {'floor':None,'reason':'tabs_not_clear'},{'floor':1},{'floor':2}]):
            self.assertIsNone(manual_floor_reading(image)['floor'])

    def test_manual_registration_searches_only_selected_floor_and_both_views(self):
        from mapmatching.src.matcher import MapMatcher
        refs=[SimpleNamespace(map_id='known',regions=[{'floor':f}]) for f in (1,2)]
        matcher=SimpleNamespace(floor_references=refs)
        sparse=replace(self.confirmed,map_id='known',floor=None,explained=.49)
        subject=SimpleNamespace(corners=[1,2,3,4])
        with patch('mapmatching.src.matcher.extract',return_value=subject) as extraction, \
             patch('mapmatching.src.matcher.retrieve',return_value=[object()]) as retrieval, \
             patch('mapmatching.src.matcher.register',side_effect=[replace(sparse),replace(sparse)]):
            result=MapMatcher.register_manual_floor(matcher,object(),'known',2)
        self.assertEqual([c.kwargs['full_view'] for c in extraction.call_args_list],[False,True])
        self.assertTrue(all(c.args[1]==[refs[1]] for c in retrieval.call_args_list))
        self.assertTrue(all(c.floor==2 for c in result.candidates))

    def test_registration_must_belong_to_current_floor_with_finite_pose(self):
        wrong=replace(self.confirmed,explained=.9)
        bad=replace(self.confirmed,floor=2,pose=Pose(float('nan'),0,0))
        good=replace(self.confirmed,floor=2,explained=.45,contradiction=.4)
        matcher=Mock();matcher.register_manual_floor.return_value=SimpleNamespace(candidates=[wrong,bad,good])
        with patch('mapmatching.src.floor_tabs.inspect_floor_tabs',return_value={'floor':2}), \
             patch('mapmatching.src.map_visibility.inspect_map_ui',return_value={'visible':True}), \
             patch('mapmatching.src.evidence.extract',return_value=SimpleNamespace(corners=[1,2,3,4],mask=SimpleNamespace(sum=lambda:100))):
            candidate,_=cross_floor_candidate(matcher,object(),self.confirmed,{})
        self.assertIs(candidate,good)

    def test_empty_floor_does_not_fit_hud_noise(self):
        matcher=Mock()
        with patch('mapmatching.src.manual_alignment.manual_floor_reading',return_value={'floor':2}), \
             patch('mapmatching.src.map_visibility.inspect_map_ui',return_value={'visible':True}), \
             patch('mapmatching.src.evidence.extract',return_value=SimpleNamespace(corners=[],mask=SimpleNamespace(sum=lambda:0))):
            self.assertEqual(cross_floor_candidate(matcher,object(),self.confirmed,{}),(None,None))
        matcher.register_manual_floor.assert_not_called()

    def test_stale_popup_cannot_start_manual_request(self):
        from mapmatching.ui import Companion
        state=ToggleState(); token=state.open(); state.close()
        subject=SimpleNamespace(state=state,manual_offer=(token,{'floor':2}),
                                dismiss_manual_offer=Mock(),retry=Mock())
        Companion.accept_manual_alignment(subject)
        subject.retry.assert_not_called()
        state.open();subject.manual_offer=(state.generation,{'floor':2})
        Companion.accept_manual_alignment(subject)
        subject.retry.assert_called_once_with(force_floor=2)

    def test_forced_and_normal_retry_return_to_game(self):
        from mapmatching.ui import Companion,C,native
        subject=SimpleNamespace(panel=Mock(),demo=None,last_external_target=123,
                                activateWindow=Mock(),open_map=Mock())
        subject.panel.isVisible.return_value=False
        with patch.object(native,'activate_target') as activate, \
             patch.object(C.QTimer,'singleShot',side_effect=lambda delay,callback:callback()):
            Companion.retry(subject,force_floor=2)
            activate.assert_called_once_with(123);subject.activateWindow.assert_not_called()
            subject.open_map.assert_called_once_with('manual_retry',force_floor=2)
            Companion.retry(subject)
            self.assertEqual(activate.call_count,2)

    def test_capture_restoration_does_not_reactivate_plugin(self):
        from mapmatching.ui import Companion
        subject=SimpleNamespace(_capture_hidden=True,keep_manual_foreground=True,activateWindow=Mock())
        with patch('mapmatching.ui.show_floating'):
            Companion.restore_capture_companion(subject)
            subject.activateWindow.assert_not_called()
            subject._capture_hidden=True;subject.keep_manual_foreground=False
            Companion.restore_capture_companion(subject)
            subject.activateWindow.assert_not_called()

    def test_blank_force_only_renders_the_opted_in_request(self):
        import tempfile
        from pathlib import Path
        import numpy as np
        from mapmatching.src.live import worker
        from mapmatching.src.matcher import MatchResult
        pixels=np.zeros((100,200,3),np.uint8)
        reference=SimpleNamespace(map_id=self.confirmed.map_id,difficulty='hard',mode=None,exclusions=[],source='map.jpg',
                                  regions=[{'floor':2,'bbox':[0,0,20,20]}])
        matcher=Mock();matcher.references=[reference]
        connection=Mock();options={'confirmed_candidate':self.confirmed}
        connection.recv.side_effect=[(1,pixels,None,options),
            (2,pixels,None,dict(options,force_floor=2)),(3,pixels,None,options),None]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'maps').mkdir();(root/'maps/index.json').write_text('{}')
            with patch('mapmatching.src.matcher.MapMatcher',return_value=matcher), \
                 patch('mapmatching.src.live.match_with_cache',side_effect=lambda *a,**k:
                       (MatchResult(candidates=[replace(self.confirmed,floor=2,retrieval_score=2)],reason='insufficient_visible_structure'),
                        replace(self.confirmed,floor=2,retrieval_score=2),'insufficient')), \
                 patch('mapmatching.src.manual_alignment.blank_floor_offer',return_value={'map_id':self.confirmed.map_id,'floor':2}), \
                 patch('mapmatching.src.manual_alignment.cross_floor_candidate',return_value=(None,None)), \
                 patch('mapmatching.src.reference.read_image',return_value=np.zeros((20,20,3),np.uint8)):
                worker(connection,root,'hard',None)
        replies=[call.args[0][1] for call in connection.send.call_args_list if call.args[0][0]=='result']
        self.assertIsNone(replies[0][1]);self.assertIsNotNone(replies[1][1]);self.assertIsNone(replies[2][1])
        self.assertTrue(replies[1][-1]['diagnostics']['manual_alignment'])
        self.assertTrue(replies[1][-1]['diagnostics']['manual_centered'])
        self.assertIsNone(replies[1][3].pose)


class PetGestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_double_click_cancels_single_click_and_retries_once(self):
        from mapmatching.ui import DraggableGear,W,C,G
        parent=W.QWidget();parent.toggle_panel=Mock();parent.retry=Mock()
        button=DraggableGear(parent)
        button.clicked.emit();self.assertTrue(button.click_timer.isActive())
        event=G.QMouseEvent(C.QEvent.MouseButtonDblClick,C.QPointF(20,20),C.QPointF(20,20),
                           C.Qt.LeftButton,C.Qt.LeftButton,C.Qt.NoModifier)
        button.mouseDoubleClickEvent(event)
        self.assertFalse(button.click_timer.isActive())
        parent.toggle_panel.assert_not_called();parent.retry.assert_called_once()
        button.exit_zone.close();button.pet.timer.stop()

    def test_popup_timeout_ignores_without_accepting_and_stops_timer(self):
        from mapmatching.ui import ManualAlignmentPopup
        popup=ManualAlignmentPopup();accepted=Mock();expired=Mock()
        popup.accepted.connect(accepted);popup.expired.connect(expired)
        with patch.object(popup,'clock') as clock:
            clock.elapsed.return_value=3000
            popup.advance()
        accepted.assert_not_called();expired.assert_called_once()
        self.assertFalse(popup.timer.isActive());self.assertFalse(popup.isVisible())
        popup.close()

    def test_dwell_resets_when_pointer_leaves(self):
        from mapmatching.ui import DraggableGear,W,C,G
        parent=W.QWidget();parent.toggle_panel=Mock();parent.retry=Mock()
        button=DraggableGear(parent);button.moved=True
        button.exit_zone.locate=Mock();button.exit_zone.setGeometry(100,100,190,90)
        with patch.object(G.QCursor,'pos',return_value=C.QPoint(150,150)):
            button.check_exit_zone()
        self.assertTrue(button.exit_clock.isValid())
        with patch.object(G.QCursor,'pos',return_value=C.QPoint(10,10)):
            button.check_exit_zone()
        self.assertFalse(button.exit_clock.isValid())
        button.moved=False;button.check_exit_zone()
        self.assertFalse(button.exit_zone.isVisible());self.assertFalse(button.exit_timer.isActive())
        button.exit_zone.close();button.pet.timer.stop()

    def test_exit_after_half_second_restores_position_before_quit(self):
        from mapmatching.ui import DraggableGear,W,C,G
        parent=W.QWidget();parent.move(30,60)
        button=DraggableGear(parent)
        event=G.QMouseEvent(C.QEvent.MouseButtonPress,C.QPointF(20,20),C.QPointF(50,80),
                           C.Qt.LeftButton,C.Qt.LeftButton,C.Qt.NoModifier)
        button.mousePressEvent(event)
        original=C.QPoint(parent.pos())
        parent.move(150,150);button.moved=True
        button.exit_zone.locate=Mock();button.exit_zone.setGeometry(100,100,190,90)
        positions=[]
        with patch.object(G.QCursor,'pos',return_value=C.QPoint(150,150)), \
             patch.object(button,'exit_clock') as clock, \
             patch.object(self.app,'quit',side_effect=lambda: positions.append(C.QPoint(parent.pos()))) as quit_app:
            clock.isValid.return_value=True
            clock.elapsed.return_value=499
            button.check_exit_zone();quit_app.assert_not_called()
            self.assertNotEqual(parent.pos(),original)
            clock.elapsed.return_value=500
            button.check_exit_zone();quit_app.assert_called_once()
        self.assertEqual(positions,[original])
        self.assertIsNone(button.origin)
        button.exit_zone.close();button.pet.timer.stop()

    def test_manual_overlay_mask_is_limited_to_map_and_normal_mode_restores_passthrough(self):
        import numpy as np
        from mapmatching.ui import Overlay,native,C
        layer=np.zeros((100,200,4),np.uint8);layer[20:50,80:120,3]=255
        overlay=Overlay()
        with patch('mapmatching.ui.show_floating'),patch.object(native,'place_overlay') as placement:
            overlay.resize(200,100)
            overlay.display(layer,(0,0,200,100),.3,manual=True)
            self.assertFalse(overlay.windowFlags() & C.Qt.WindowTransparentForInput)
            self.assertTrue(overlay.mask().contains(C.QPoint(90,30)))
            self.assertFalse(overlay.mask().contains(C.QPoint(5,5)))
            placement.assert_called_with(int(overlay.winId()),(0,0,200,100),interactive=True)
            overlay.display(layer,(0,0,200,100),.3)
            self.assertTrue(overlay.windowFlags() & C.Qt.WindowTransparentForInput)
            self.assertTrue(overlay.mask().isEmpty())
        overlay.close()
