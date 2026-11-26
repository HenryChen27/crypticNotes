"""Source contracts for the idle map probe (IdleMapProbe / CaptureService).

Device behaviour was measured, not simulated: Xiaomi 15 Pro, game at 60 fps,
SurfaceFlinger timestats over 15 s windows, six rounds in rotating order
(2026-11-15). Frames presented 33 ms or later after the previous one:

    surface attached once and left attached      18.5   (SF-attributed jank  6.0)
    attach -> one frame -> detach, every second  30.8   (SF-attributed jank 23.2, a 50 ms frame in every window)
    no probing, surface detached                 33.8   (SF-attributed jank 19.7)

Each surface change makes SurfaceFlinger rebuild the virtual display, so the
once-a-second pulse put a rhythmic pair of late frames into the game. These
checks keep the probe from sliding back to that.
"""
from pathlib import Path
import unittest

JAVA=Path(__file__).resolve().parents[1]/'app/src/main/java/com/crypticnotes/mobile'
PROBE=(JAVA/'IdleMapProbe.java').read_text(encoding='utf-8')
SERVICE=(JAVA/'CaptureService.java').read_text(encoding='utf-8')


class IdleProbeContractTests(unittest.TestCase):
    def test_delivering_a_frame_does_not_detach_the_surface(self):
        finish=PROBE.split('private void finish(',1)[1].split('\n    }',1)[0]
        self.assertNotIn('setSurface',finish,'取到一帧又把虚拟屏断开了：每秒一次接上/断开会让游戏成对丢帧')
        self.assertNotIn('cancel()',finish)

    def test_an_attached_probe_only_reads_the_latest_frame(self):
        start=PROBE.split('void start(',1)[1].split('cancel();',1)[0]
        self.assertIn('attached',start)
        self.assertIn('result.ready(latest(reader))',start)
        self.assertNotIn('setSurface',start,'已接上时不应再改虚拟屏的输出')

    def test_only_cancel_detaches(self):
        self.assertEqual(PROBE.count('setSurface(null)'),2,'断开只应出现在首次接上前和 cancel() 里')
        cancel=PROBE.split('void cancel(){',1)[1].split('\n    }',1)[0]
        self.assertIn('owner.setSurface(null)',cancel)
        self.assertIn('attached=false',cancel)

    def test_idle_capture_output_leaves_an_attached_probe_alone(self):
        update=SERVICE.split('private void updateCaptureOutput(){',1)[1].split('\n    }',1)[0]
        self.assertIn('if(!idleProbe.attached())display.setSurface(null);',update)

    def test_switching_the_automatic_check_off_releases_the_mirror(self):
        tick=SERVICE.split('private final Runnable idleProbeTick=()->{',1)[1].split('\n    };',1)[0]
        self.assertIn('if(!automaticMapProbe())idleProbe.cancel();',tick)
        home=(JAVA/'MainActivity.java').read_text(encoding='utf-8')
        self.assertIn('putBoolean("automatic_map_probe",value).apply();pushDisplayPreferences()',home)
        self.assertIn('refreshTapRegion()',SERVICE.split('void applyDisplayPreferences()',1)[1].split('\n    }',1)[0])
        refresh=SERVICE.split('private void refreshTapRegion()',1)[1].split('\n    }',1)[0]
        self.assertIn('if(automaticMapProbe())scheduleIdleProbe()',refresh)
        self.assertIn('main.removeCallbacks(idleProbeTick);idleProbeScheduled=false;idleProbe.cancel()',refresh)

    def test_overlay_only_has_match_actions_not_management(self):
        panel=SERVICE.split('private void showQuickSettings()',1)[1].split('\n    }',1)[0]
        for removed in ('地图设置','自动检测地图','复制识图诊断','版本管理','mapOptions'):
            self.assertNotIn(removed,panel)
        for kept in ('重新识别','隐藏叠图','屏幕录制','libraryChoice.detachProvider()','launch_game'):
            self.assertIn(kept,panel)
        home=(JAVA/'MainActivity.java').read_text(encoding='utf-8')
        for setting in ('地图设置','复制识图诊断','自动展开检测','小游戏设置'):
            self.assertIn(setting,home)

    def test_no_measurement_switch_is_left_in_the_service(self):
        self.assertNotIn('probe_mode',SERVICE)


if __name__=='__main__': unittest.main()
