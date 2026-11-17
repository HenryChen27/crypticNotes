"""The replay buffer ("save the last 30 seconds").

Two kinds of check. The buffer itself is plain Java, so its eviction and
clip rules are compiled and run here on the desktop JVM
(`ReplayBufferTest.java`). Everything around it -- encoder, surfaces, the
gallery -- only exists on a phone, so those are source contracts: they keep the
few rules that are easy to break by editing from being broken silently.

Measured once on a device (Xiaomi 15 Pro, 2026-11-16, see android/README.md):
with the buffer on the game showed no more late frames than with it off, at
14-52% of one core for the plugin process. One phone, one match, six minutes --
heat and battery over a long session are still unknown, which is why the switch
defaults to off.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
JAVA=ROOT/'android/app/src/main/java/com/crypticnotes/mobile'
JDK=ROOT/'out/android-tools/jdk/jdk-17.0.20.1+1/bin'
RECORDER=(JAVA/'SharedScreenRecorder.java').read_text(encoding='utf-8')
SERVICE=(JAVA/'CaptureService.java').read_text(encoding='utf-8')
PRESETS=(JAVA/'RecordPresets.java').read_text(encoding='utf-8')
BUFFER=(JAVA/'ReplayBuffer.java').read_text(encoding='utf-8')


def method(source,signature):
    """Text of one method, from its signature to the next member at the same depth."""
    return source.split(signature,1)[1].split('\n    }\n',1)[0]


class ReplayBufferTests(unittest.TestCase):
    @unittest.skipUnless((JDK/'javac.exe').exists(),'JDK from out/android-tools is not installed')
    def test_buffer_rules_on_the_desktop_jvm(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([str(JDK/'javac.exe'),'-encoding','UTF-8','-d',out,str(JAVA/'ReplayBuffer.java'),
                            str(ROOT/'android/tests/ReplayBufferTest.java')],check=True)
            result=subprocess.run([str(JDK/'java.exe'),'-cp',out,'com.crypticnotes.mobile.ReplayBufferTest'],
                                  capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Replay buffer tests passed',result.stdout)

    def test_buffer_stays_plain_java(self):
        self.assertNotIn('import android',BUFFER,'ReplayBuffer 用了 android.*，桌面 JVM 上就跑不了它的测试')

    def test_switch_defaults_to_off(self):
        self.assertIn('getInt(KEY_REPLAY, 0)',PRESETS,'回溯录制必须默认关闭：编码器常开的代价还没在手机上量过')

    def test_lengths_on_offer_and_the_button_that_names_them(self):
        self.assertIn('REPLAY_SECONDS = {0, 20, 30, 40, 50}',PRESETS)
        self.assertIn('return "回溯录屏（" + seconds + "s）";',PRESETS)
        # One wording for the panel button and the notification action.
        self.assertEqual(SERVICE.count('RecordPresets.replayLabel('),2)
        self.assertNotIn('保存前 "+',SERVICE.split('replaySaved(',1)[0],'按钮上还留着旧的「保存前 N 秒」写法')

    def test_changing_the_length_restarts_the_buffer(self):
        changed=method(SERVICE,'void replaySettingChanged() {')
        self.assertIn('wanted!=replaySeconds) stopRecording();',changed,
                      '时长改了，正在跑的缓冲大小就不对了，必须停掉让它按新时长重开')

    def test_replay_session_creates_no_file_until_asked(self):
        prepare=method(RECORDER,'private void prepare() throws Exception {')
        self.assertIn('if(replaySeconds==0) {\n            output=new RecordingFile(',prepare,
                      '回溯模式一开始就建了视频文件：它应该只在内存里攒，按下保存才写')
        write=method(RECORDER,'private void writeSample(')
        self.assertLess(write.index('replay.add('),write.index('muxer.writeSampleData('),
                        '回溯模式的数据必须先进内存缓冲，不能落到直接写文件那条路上')

    def test_saving_does_not_stall_the_encoder(self):
        save=method(RECORDER,'void saveReplay() {')
        self.assertIn('new Thread(',save,'保存片段必须在另一条线程上封装，否则写文件期间编码器没人排空')
        self.assertNotIn('MediaMuxer',save)
        self.assertIn('savingReplay.compareAndSet(false,true)',save,'连按两次不能同时写两个文件')

    def test_one_key_frame_a_second_while_buffering(self):
        self.assertIn('KEY_I_FRAME_INTERVAL,replaySeconds>0?1:2',RECORDER,
                      '片段只能从关键帧开始：回溯模式每秒一个，存下来的长度才不会比要的多出两秒')

    def test_buffer_is_not_treated_as_a_recording_the_user_started(self):
        pulse=method(SERVICE,'private void updateRecordingPulse() {')
        self.assertIn('|| replaySession)',pulse,'回溯缓冲常开，悬浮球不能因此一直闪')
        hold=method(SERVICE,'private void handleBadgeHold() {')
        self.assertIn('if(recorder!=null && !replaySession) {',hold,'长按悬浮球应该照常关闭识别，而不是去“停止录屏”')

    def test_buffer_only_runs_in_landscape_map_mode_and_never_restarts_after_an_error(self):
        ensure=method(SERVICE,'void ensureReplay() {')
        for guard in ('gameOnly','replayFailed','width<=height','recorder!=null','pendingRecording'):
            self.assertIn(guard,ensure)
        self.assertIn('if(replaySession)stopRecording();',method(SERVICE,'void openGame(String id){'),
                      '进小游戏模式后不该再录屏幕')

    def test_recording_takes_the_encoder_over_from_the_buffer(self):
        toggle=method(SERVICE,'private void toggleRecording() {')
        self.assertIn('pendingRecording=true; stopRecording(); return;',toggle)
        self.assertIn('if(pendingRecording) { pendingRecording=false; startRecorder(false); }',SERVICE)

    def test_measurement_hook_is_gone(self):
        self.assertNotIn('MEASURE_HOOK',SERVICE,'测量用的临时开关还留在服务里')
        for name in ('replay_mode','replay_save','replay_state'):
            self.assertNotIn(name,SERVICE)


if __name__=='__main__':
    unittest.main()
