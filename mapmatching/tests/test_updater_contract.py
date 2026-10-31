"""Source-level contracts for the Windows updater (`scripts/update-client.ps1`).

These check the source text, not the behaviour.  Running the updater for real
replaces an installation and needs a release to download, so the ordinary test
suite cannot exercise it -- but the two decisions guarded here are exactly the
ones that made a *successful* update look like a dead button, and they were
both invisible from the log:

  * the updater window opened non-topmost, behind the fullscreen game and the
    user's editor, so the progress dialog was never seen;
  * a second click while that window was still open exited silently on the
    mutex, printing and showing nothing at all.

The bytes matter as much as the logic here: `dist_extras.py` rejects a copy
that lost its UTF-8 BOM or grew a bare LF, and that rejection happens inside
packaging -- i.e. after the bug would already be in a shipped zip.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT/'scripts/update-client.ps1'


def read(path):
    # Explicit utf-8: the default codepage on this machine is cp936 and this
    # file contains Chinese.
    return path.read_text(encoding='utf-8')


class UpdaterContractTests(unittest.TestCase):
    def setUp(self):
        self.source = read(UPDATER)

    def test_mutex_busy_says_something_instead_of_exiting_silently(self):
        branch = self.source.split('if (-not $locked)', 1)[1].split('\n}', 1)[0]
        self.assertIn('Show-Notice', branch,
                      '抢不到锁时又变成静默 exit 了：用户点更新会毫无反应，日志里也什么都没有')
        self.assertNotIn('exit', branch.split('Show-Notice', 1)[0],
                         'Show-Notice 必须在那句 exit 之前，否则提示还没弹就退出了')

    def test_notice_dialogs_have_a_topmost_owner(self):
        # A bare MessageBox lands behind the game exactly like the main window
        # did, which is the bug these notices exist to report.
        owner = self.source.split('function New-NoticeOwner', 1)[1].split('\n}', 1)[0]
        self.assertIn('TopMost = $true', owner,
                      'New-NoticeOwner 的宿主窗口不置顶，提示会开在游戏后面，等于没说')
        for name in ('Show-Notice', 'Confirm-Redownload'):
            body = self.source.split('function ' + name, 1)[1].split('\n}', 1)[0]
            self.assertIn('New-NoticeOwner', body,
                          name + ' 没用置顶宿主，弹窗会开在游戏后面')

    def test_latest_version_asks_instead_of_refusing(self):
        # "已经是最新版本" used to stop dead. A player who deleted files by accident
        # then had no way back: the button said it was up to date and did nothing.
        index = self.source.index("$label.Text = '已经是最新版本'")
        guard = next(line for line in reversed(self.source[:index].splitlines())
                     if line.lstrip().startswith('if ('))
        self.assertIn('Confirm-Redownload', guard,
                      '已是最新的分支又变回直接拒绝了：误删文件的玩家没法用更新按钮修复')

    def test_redownload_prompt_defaults_to_no(self):
        # 默认按钮是「是」的话，随手一个回车就开始下 240MB。
        function = self.source.split('function Confirm-Redownload', 1)[1].split('\n}', 1)[0]
        self.assertIn("'YesNo'", function, '没问「要不要重新下载」，直接就开始重下了')
        self.assertIn("'Button2'", function,
                      '重新下载的确认框默认落在「是」上，误按回车就会白下 240MB')

    def test_repair_run_reports_a_distinct_result(self):
        # 重装和真更新要能分辨，否则测试时看不出到底走了哪条路。
        parts = self.source.split('$label.Text = if ($redownload)', 1)
        self.assertEqual(len(parts), 2,
                         '重新下载完成后没有单独的文案，分不清是「更新了」还是「重装了一遍」')

    def test_progress_window_is_topmost(self):
        form = self.source.split('$form = [Windows.Forms.Form]::new()', 1)[1].split('$form.Show()', 1)[0]
        self.assertIn('$form.TopMost = $true', form,
                      '更新窗口不置顶就会开在游戏/编辑器后面，一次成功的更新看起来像没反应')

    def test_older_channel_build_cannot_replace_newer_installation(self):
        guard=self.source.index('[long]$remote.build -lt [long]$local.build')
        download=self.source.index('Download $asset[0].browser_download_url')
        self.assertLess(guard,download)
        self.assertIn('throw',self.source[guard:guard+160])

    def test_keeps_the_utf8_bom_and_crlf_dist_extras_requires(self):
        data = UPDATER.read_bytes()
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'),
                        '丢了 UTF-8 BOM：PowerShell 5.1 会按 GBK 读，中文全变乱码')
        self.assertEqual(data.count(b'\n') - data.count(b'\r\n'), 0,
                         '出现了裸 LF：dist_extras 会在打包时拒绝这个文件')


if __name__ == '__main__':
    unittest.main()
