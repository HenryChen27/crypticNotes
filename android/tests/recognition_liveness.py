"""Scheduling contracts for CaptureService; device timing still needs replay."""
from pathlib import Path
import unittest

SOURCE=(Path(__file__).resolve().parents[1]/
    'app/src/main/java/com/crypticnotes/mobile/CaptureService.java').read_text(encoding='utf-8')


class LivenessTests(unittest.TestCase):
    def test_idle_recognition_is_not_preempted_by_visibility_heartbeat(self):
        sample=SOURCE.split('private void sample() {',1)[1].split('private void blink()',1)[0]
        self.assertIn('(overlayLayer != null || busy) &&',sample)
        self.assertLess(sample.index('manualRetry && !busy'),sample.index('lastGateAt >= 800'))

    def test_slow_inspection_restarts_heartbeat_clock_on_completion(self):
        callback=SOURCE.split('final boolean passed = visible, ran = ok;',1)[1]
        self.assertLess(callback.index('lastGateAt = SystemClock.elapsedRealtime();'),
                        callback.index('token != generation'))

    def test_missing_async_callback_does_not_disable_watchdog(self):
        poll=SOURCE.split('private final Runnable poll =',1)[1].split('@Override public IBinder',1)[0]
        self.assertIn('finally {',poll)
        self.assertIn('!pollScheduled) repoll(500)',poll)
        sample=SOURCE.split('private void sample() {',1)[1].split('private void blink()',1)[0]
        self.assertLess(sample.index('boolean overdue'),sample.index('if (checking)'))

    def test_manual_retry_is_acknowledged_and_queued(self):
        retry=SOURCE.split('private void retryFromBadge() {',1)[1].split('private float badgeDownX',1)[0]
        self.assertIn('badgeText = ""',retry)
        self.assertIn('manualRetry = true',retry)
        self.assertNotIn('busy = false',retry)
        self.assertNotIn('checking = false',retry)


if __name__=='__main__': unittest.main()
