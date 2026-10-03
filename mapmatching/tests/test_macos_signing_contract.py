"""Source-level contracts for the macOS code signing path.

These check the source text, not the behaviour: signing needs macOS, a real
keychain and codesign(1), so none of it can run on the Windows dev machine or
in the ordinary test suite.  What is checkable -- and what actually regressed
once already -- is the set of decisions that silently produce a *working build
that is ad-hoc signed anyway*, which is invisible until users lose their
Screen Recording and Input Monitoring grants on the next update.
"""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'scripts/build_macos.py'
WORKFLOW=ROOT/'.github/workflows/macos.yml'
INPUT=ROOT/'mapmatching/macos_input.py'


def read(path):
    # Explicit utf-8: the default codepage on this machine is cp936 and these
    # files contain Chinese.
    return path.read_text(encoding='utf-8')


def argument_lists(source):
    """Every bracket-delimited literal, i.e. a real argv, not prose."""
    return re.findall(r'\[[^\[\]]*\]',source)


def elements(bracket):
    return re.findall(r"'([^']*)'",bracket)


class SigningContractTests(unittest.TestCase):
    def setUp(self):
        self.build=read(BUILD)
        self.workflow=read(WORKFLOW)

    def test_identity_lookup_never_filters_by_validity(self):
        # The single highest-value assertion here.  A freshly imported
        # self-signed certificate reports CSSMERR_TP_NOT_TRUSTED, so
        # `find-identity -v` prints "0 valid identities found", the lookup
        # misses, and the build falls back to ad-hoc signing while looking
        # completely healthy.
        lists=[b for b in argument_lists(self.build) if 'find-identity' in b]
        self.assertTrue(lists,'build_macos.py 里找不到 find-identity 调用')
        for bracket in lists:
            self.assertNotIn('-v',elements(bracket),
                'find-identity 不能带 -v：自签名证书会被当成"无效"滤掉，导致静默回落 ad-hoc')

    def test_signing_disables_the_apple_timestamp_server(self):
        # A self-signed certificate cannot be stamped by Apple's TSA; leaving
        # the default on makes codesign fail or hang.
        lists=[b for b in argument_lists(self.build) if "'--sign'" in b]
        self.assertTrue(lists,'build_macos.py 里找不到 codesign --sign 调用')
        for bracket in lists:
            self.assertIn('--timestamp=none',elements(bracket),
                'codesign 必须带 --timestamp=none，否则会去 Apple 时间戳服务器')

    def test_deep_is_only_ever_used_for_verification(self):
        # --deep is a verification flag that Apple deprecated for signing; on a
        # PyInstaller --onedir bundle it signs nested code in an unspecified
        # order.  Signing is done inside-out instead.
        for bracket in argument_lists(self.build):
            if '--deep' in bracket:
                self.assertIn('--verify',elements(bracket),
                    '--deep 只能出现在校验调用里，不能用来签名')

    def test_hardened_runtime_and_entitlements_are_not_enabled(self):
        # Hardened runtime enables library validation, which demands one Team ID
        # across every loaded library, and a self-signed certificate has none.
        # It is a notarization prerequisite, not a Gatekeeper bypass.
        for bracket in argument_lists(self.build):
            for flag in elements(bracket):
                self.assertFalse(flag.startswith('--options'),
                    f'不该开 hardened runtime: {flag}')
                self.assertNotIn(flag,('--entitlements',),
                    '自签名包不该加 entitlements')

    def test_designated_requirement_is_asserted_after_signing(self):
        # This is the check that catches an ad-hoc fallback: an ad-hoc DR reads
        # `identifier "..." and cdhash H"..."`, which changes every build.
        self.assertIn('certificate leaf[subject.CN]',self.build)
        # The hash form is not decoration.  A macos-14 runner emitted
        # `certificate root = H"a57b1d48..."` rather than the by-name form,
        # because a self-signed certificate that is not in the trust store has
        # no anchor to name.  Dropping it would fail every build.
        self.assertIn('certificate root = H"',self.build,
            '自签名证书不受信任时 codesign 会钉证书哈希，这个形态必须被接受')
        self.assertIn('cdhash',self.build)

    def test_designated_requirement_reads_both_output_streams(self):
        # `codesign -d -r- --verbose=4` splits its output: the verbose dump goes
        # to stderr, the requirement itself to stdout.  A check that reads only
        # stderr finds no `designated =>` line and fails the build on a bundle
        # that is in fact correctly signed -- which is exactly what happened on
        # the first macos-14 runner.
        self.assertIn('result.stdout',self.build,
            'DR 断言必须合并 codesign 的两个输出流，只读 stderr 会漏掉要求本身')
        self.assertIn('result.stderr',self.build)

    def test_missing_certificate_fails_the_build(self):
        # Never degrade to unsigned: that is the exact silent path this whole
        # change exists to close.  The escape hatch stays explicit and named.
        self.assertIn('MACOS_SIGNING_IDENTITY',self.build)
        self.assertIn('MACOS_SKIP_SIGNING',self.build)
        self.assertNotIn('MACOS_SKIP_SIGNING',self.workflow,
            'CI 绝不能跳过签名，否则会发出版本号正常但没有签名的包')

    def test_workflow_imports_and_cleans_up_the_certificate(self):
        self.assertIn('set-key-partition-list',self.workflow,
            '少了 set-key-partition-list，codesign 会在 runner 上卡在密码框')
        self.assertIn('security import',self.workflow)
        self.assertIn('if: always()',self.workflow,
            '临时钥匙串必须在 job 结束后无条件删除')

    def test_diagnostic_ships_beside_the_bundle(self):
        # Inside the .app it would break the code seal and fail --verify --strict,
        # so it travels as a sibling and the archive is built from the directory
        # instead of --keepParent-ing the bundle.
        self.assertIn('diagnose_macos.command',self.build)
        ditto=[b for b in argument_lists(self.build) if 'ditto' in b]
        self.assertTrue(ditto,'build_macos.py 里找不到 ditto 调用')
        for bracket in ditto:
            self.assertNotIn('--keepParent',elements(bracket),
                '要对 dist-macos 目录打包，--keepParent 会把诊断脚本挡在压缩包外')

    def test_collect_directory_is_dropped_before_packaging(self):
        # --onedir --windowed emits both dist-macos/加页手记/ (COLLECT) and
        # dist-macos/加页手记.app/ (BUNDLE).  Archiving the directory instead of
        # the bundle therefore carries both copies and roughly doubles the ZIP.
        # The removal has to come *before* ditto; after it is no-op.
        self.assertLess(self.build.index('shutil.rmtree(collect)'),
                        self.build.index("['ditto'"),
                        '必须先删掉 COLLECT 目录再打包，否则 zip 里有两份拷贝')


class InputMonitoringContractTests(unittest.TestCase):
    def test_input_monitoring_is_actually_requested(self):
        # Passive polling via CGEventSourceKeyState never raises the prompt and
        # never creates the System Settings entry, so the app cannot be found in
        # 输入监控 and the hotkeys silently do nothing.  No signature change
        # fixes that; only an explicit request does.
        source=read(INPUT)
        self.assertIn('CGRequestListenEventAccess',source,
            '必须显式申请输入监控，否则应用不会出现在系统设置的列表里')
        self.assertIn('CGPreflightListenEventAccess',source)


if __name__=='__main__':
    unittest.main()
