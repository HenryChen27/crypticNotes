"""Startup ordering regression checks; not a replacement for device touch tests."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/crypticnotes/mobile'


class FirstStartContract(unittest.TestCase):
    def test_settings_are_available_before_matcher_ready(self):
        source = (ROOT / 'CaptureService.java').read_text(encoding='utf-8')
        panel = source.split('private void showQuickSettings() {', 1)[1]
        guard = panel.split('clearOverlay();', 1)[0]
        self.assertNotIn('!ready', guard)
        self.assertIn('preparationLabel.setVisibility(initializing', panel)
        self.assertIn('retry.setOnClickListener(v -> retryFromBadge())', panel)

    def test_initialization_does_not_override_pending_settings(self):
        source = (ROOT / 'CaptureService.java').read_text(encoding='utf-8')
        completion = source.split('initializing = false;', 1)[1].split('});', 1)[0]
        self.assertIn('ready = !applying;', completion)
        self.assertIn('if (ready) repoll(0)', completion)
        self.assertIn('Executors.newSingleThreadExecutor()', source)

    def test_notification_dialog_finishes_before_projection_request(self):
        source = (ROOT / 'MainActivity.java').read_text(encoding='utf-8')
        start = source.split('private void startCapture() {', 1)[1].split('@Override', 1)[0]
        request = start.split('requestPermissions(', 1)[1]
        self.assertLess(request.index('return;'), request.index('requestCapturePermission();'))
        callback = source.split('void onRequestPermissionsResult(', 1)[1].split('private void', 1)[0]
        self.assertIn('if (request == 2) requestCapturePermission();', callback)


if __name__ == '__main__':
    unittest.main()
