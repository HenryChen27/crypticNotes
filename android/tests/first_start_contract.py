"""Startup ordering regression checks; not a replacement for device touch tests."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/crypticnotes/mobile'


class FirstStartContract(unittest.TestCase):
    def test_settings_order_and_mailbox_reentry(self):
        source = (ROOT / 'MainActivity.java').read_text(encoding='utf-8')
        general = source.split('content=generalPage;', 1)[1]
        self.assertLess(general.index('generalPage.addView(batch,'), general.index('mailSection=fold("邮箱",true)'))
        self.assertLess(general.index('mailSection.addView(mailbox,'), general.index('fold("悬浮球",false)'))
        self.assertEqual(source.count('"一键更新"'), 1)
        navigation = source.split('private void switchModule(', 1)[1].split('private LinearLayout newPage', 1)[0]
        self.assertIn('"settings".equals(name)&&!name.equals(activeModule)', navigation)
        self.assertIn('setFoldExpanded(mailSection,true)', navigation)
        self.assertNotIn('MailboxSync.open', navigation)

    def test_mail_body_and_open_receipt_belong_to_the_visible_reader(self):
        listing = (ROOT / 'MailboxView.java').read_text(encoding='utf-8')
        reader = (ROOT / 'MailReaderDialog.java').read_text(encoding='utf-8')
        self.assertIn('MailReaderDialog.open(', listing.split('row.setOnClickListener', 1)[1])
        self.assertNotIn('mail.body', listing)
        self.assertNotIn('MailboxSync.open(', listing)
        build, shown = reader.split('void onStart()', 1)
        self.assertNotIn('MailboxSync.open(', build)
        self.assertLess(shown.index('super.onStart()'), shown.index('MailboxSync.open('))
        self.assertIn('scroll.addView(content)', build)
        for field in ('title', 'body'):
            self.assertIn('content.addView(' + field + ')', build)
        self.assertNotRegex(build, r'\.(setMaxLines|setEllipsize|setSingleLine)\(')
        self.assertIn('setPositiveButton("关闭"', build)

    def test_power_saving_uses_existing_preference_inside_system_settings(self):
        source = (ROOT / 'MainActivity.java').read_text(encoding='utf-8')
        system = source.split('systemSettings=fold("系统设置",true)', 1)[1].split('fold("版本", false)', 1)[0]
        self.assertIn('systemSettings.addView(choiceRow(Theme.helpLabel(this,"省电模式"', system)
        self.assertIn('getBoolean("power_saving",false)', system)
        self.assertIn('putBoolean("power_saving",i==1)', system)
        self.assertNotIn('fold("界面设置"', source)

    def test_opacity_controls_stay_in_main_map_settings_not_the_overlay(self):
        source = (ROOT / 'CaptureService.java').read_text(encoding='utf-8')
        panel = source.split('private void showQuickSettings() {', 1)[1].split('windows.addView(shell, p);', 1)[0]
        home = (ROOT / 'MainActivity.java').read_text(encoding='utf-8')
        for control in ('opacityLabel', 'slider'):
            with self.subTest(control=control):
                pattern = r'(\w+)\.addView\(\s*' + control + r'\b'
                self.assertEqual(re.findall(pattern, panel), [])
                self.assertEqual(re.findall(pattern, home), ['mapSettings'])

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
        self.assertNotRegex(completion, r'(?m)^\s*applying\s*=(?!=)')
        self.assertRegex(completion, r'if\s*\(ready\)\s*\{\s*sleepRecognition\(\);')
        self.assertEqual(completion.count('sleepRecognition();'), 1)
        self.assertNotIn('repoll(', completion)
        sleep = source.split('private void sleepRecognition(){', 1)[1].split('\n    }', 1)[0]
        self.assertIn('main.removeCallbacks(poll)', sleep)
        self.assertIn('scheduleIdleProbe();', sleep)
        self.assertNotIn('repoll(', sleep)
        probe = source.split('private void scheduleIdleProbe(){', 1)[1].split('\n    }', 1)[0]
        self.assertRegex(probe, r'if\s*\([^\n;]*!ready[^\n;]*\)\s*return;')
        self.assertIn('main.postDelayed(idleProbeTick,', probe)
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
