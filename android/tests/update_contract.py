"""Update path: one download, one install, and the order they must happen in.

The update used to be wholly owned by the settings screen. Moving the transfer
into a service is exactly the kind of change that quietly leaves two copies of
it behind, so these check the source, not the behaviour -- there is no device in
the loop and a real install cannot be simulated here.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'app/src/main/java/com/crypticnotes/mobile'
MANIFEST = (ROOT / 'app/src/main/AndroidManifest.xml').read_text(encoding='utf-8')


class UpdateContract(unittest.TestCase):
    def test_service_is_declared_as_data_sync(self):
        self.assertIn('FOREGROUND_SERVICE_DATA_SYNC', MANIFEST)
        self.assertIn('android.permission.WAKE_LOCK', MANIFEST)
        service = MANIFEST.split('.UpdateService', 1)[1].split('/>', 1)[0]
        self.assertIn('android:foregroundServiceType="dataSync"', service)
        # A background-download service must not be startable by other apps.
        self.assertIn('android:exported="false"', service)

    def test_only_one_place_downloads_the_package(self):
        # The settings screen still fetches the release JSON over HttpURLConnection;
        # what it must no longer do is write the package anywhere.
        updater = (JAVA / 'AppUpdater.java').read_text(encoding='utf-8')
        self.assertNotIn('new FileOutputStream', updater)
        self.assertNotIn('renameTo', updater)
        self.assertNotIn('MessageDigest', updater, 'the transfer kept its own checksum')
        self.assertIn('UpdateService.start(', updater)
        self.assertIn('new FileOutputStream', (JAVA / 'UpdateService.java').read_text(encoding='utf-8'))

    def test_bytes_are_verified_before_they_can_be_installed(self):
        service = (JAVA / 'UpdateService.java').read_text(encoding='utf-8')
        body = service.split('private void download(', 1)[1]
        self.assertLess(body.index('sha.digest()'), body.index('AppInstaller.verify('))
        self.assertLess(body.index('AppInstaller.verify('), body.index('AppInstaller.apk(this)'))
        # Half-written bytes must never sit at the path the provider serves.
        self.assertLess(body.index('AppInstaller.partial(this)'), body.index('AppInstaller.apk(this)'))
        self.assertNotIn('new FileOutputStream(AppInstaller.apk', service)

    def test_install_is_reachable_from_a_background_context(self):
        installer = (JAVA / 'AppInstaller.java').read_text(encoding='utf-8')
        intent = installer.split('Intent installer = new Intent(Intent.ACTION_VIEW)', 1)[1].split(';', 1)[0]
        # Without NEW_TASK a start from the service throws; from the settings
        # screen it is merely redundant, so it has to be there unconditionally.
        self.assertIn('FLAG_ACTIVITY_NEW_TASK', intent)
        self.assertIn('FLAG_GRANT_READ_URI_PERMISSION', intent)
        self.assertIn('stopService(new Intent(context, CaptureService.class))', installer)

    def test_a_dropped_background_launch_still_leaves_something_to_tap(self):
        service = (JAVA / 'UpdateService.java').read_text(encoding='utf-8')
        success = service.split('AppInstaller.install(this);', 1)[1].split('publish(', 1)[0]
        self.assertIn('AppInstaller.ready(this', success)
        installer = (JAVA / 'AppInstaller.java').read_text(encoding='utf-8')
        self.assertIn('static boolean takePending(', installer)
        self.assertIn('AppInstaller.takePending(activity)', (JAVA / 'AppUpdater.java').read_text(encoding='utf-8'))

    def test_recording_defaults_match_the_old_fixed_behaviour(self):
        presets = (JAVA / 'RecordPresets.java').read_text(encoding='utf-8')
        self.assertIn('DEFAULT_QUALITY_ID = "standard"', presets)
        self.assertIn('DEFAULT_FPS = 24', presets)
        self.assertIn('QUALITY_LONG_SIDE = {720, 1280, 1920}', presets)
        self.assertIn('QUALITY_BITRATE = {2_000_000, 4_000_000, 8_000_000}', presets)
        # Internal sound is the requested default now; the switch and the
        # recorder ask different questions of the same key, on purpose.
        self.assertIn('KEY_AUDIO, true', presets)

    def test_recorder_paces_frames_at_the_chosen_rate(self):
        recorder = (JAVA / 'SharedScreenRecorder.java').read_text(encoding='utf-8')
        self.assertIn('1_000_000_000L/videoFps', recorder)
        self.assertIn('KEY_FRAME_RATE,videoFps', recorder)
        self.assertIn('KEY_BIT_RATE,videoBitrate', recorder)
        # The frame rate is only knowable after the codec is queried, so the
        # literal that used to be here must not have survived anywhere.
        self.assertNotIn('/24', recorder.split('private void frame()', 1)[1].split('}', 1)[0])


if __name__ == '__main__':
    unittest.main()
