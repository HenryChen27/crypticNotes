"""Generate the self-signed code-signing certificate the macOS build signs with.

Run this once, then paste the two printed values into the GitHub repository
secrets (Settings -> Secrets and variables -> Actions).

Why a certificate at all: macOS TCC binds a permission grant to the code's
Designated Requirement (DR) captured at the moment of the grant.

    ad-hoc signature -> DR pins the cdhash  -> changes every build -> grant lost
    certificate      -> DR pins the leaf CN -> stable across builds -> grant kept

That is the whole difference; nothing else about the app changes.

Two things must never change afterwards:

* **The CN.** The DR is literally
  ``identifier "com.henrychen.crypticnotes" and certificate leaf[subject.CN] = "<CN>"``
  so a different CN is a different app to TCC and every existing user has to
  grant Screen Recording and Input Monitoring again from scratch.  Renew with
  the *same* CN and old grants keep working -- the DR contains no key material,
  so it survives losing the private key.  Changing the CN does not.
* **That the private key stays private.**  Anyone holding it can produce a
  binary that already-granted machines will accept.  Gatekeeper still blocks
  such a build (it is quarantined and unnotarized), but the posture is weaker
  than a Developer ID, so treat the .p12 like a password.
"""
from pathlib import Path
import argparse
import base64
import secrets
import string
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out/macos-signing'

# ASCII and space separated on purpose: this string ends up verbatim inside the
# designated requirement and has to survive quoting in Git Bash, PowerShell and
# bash on the runner.  A CJK CN would be a shell-quoting hazard for no benefit.
CN = 'IdentityVMapAssistant Self-Signed Code Signing'

P12_PASSWORD_SECRET = 'MACOS_SIGNING_P12_PASSWORD'
P12_SECRET = 'MACOS_SIGNING_P12'

# `openssl asn1parse` prints digest algorithm identifiers by name, not by OID --
# it says `:sha1`, never `1.3.14.3.2.26`.  Measured against both formats.
SHA1_MAC = 'sha1'
SHA256_MAC = 'sha256'


def run(args):
    """Run openssl, echo the command, and fail loudly with its stderr."""
    print('  $', ' '.join(args), flush=True)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'openssl 失败 ({result.returncode}):\n{result.stderr.strip()}')
    return result.stdout


def check_openssl():
    try:
        version = run(['openssl', 'version'])
    except FileNotFoundError:
        raise SystemExit('找不到 openssl。Windows 上 Git Bash 自带；请确认它在 PATH 里。')
    print(version.strip())
    # -addext only exists from 1.1.1 onwards, and the cert extensions are the
    # whole reason the identity is usable for code signing.
    if version.split()[1] < '1.1.1':
        raise SystemExit('openssl 版本过低（需要 >= 1.1.1 才有 -addext）。')


def generate(password):
    key = OUT / 'key.pem'
    crt = OUT / 'codesign.crt'
    p12 = OUT / 'codesign.p12'
    run(['openssl', 'req', '-x509', '-newkey', 'ec',
         '-pkeyopt', 'ec_paramgen_curve:P-256', '-sha256', '-days', '3650', '-nodes',
         '-keyout', str(key), '-out', str(crt),
         '-subj', f'/CN={CN}/O=HenryChen/C=CN',
         '-addext', 'basicConstraints=critical,CA:FALSE',
         '-addext', 'keyUsage=critical,digitalSignature',
         '-addext', 'extendedKeyUsage=codeSigning',
         '-addext', 'subjectKeyIdentifier=hash'])
    # -legacy, unconditionally.  OpenSSL 3 switched the default PKCS#12 MAC to
    # SHA-256, and `security import` on macOS 14 answers that with
    #     SecKeychainItemImport: MAC verification failed during PKCS12 import
    # which reads exactly like a wrong password and sends you hunting for a
    # password bug that is not there.  Measured on a macos-14 runner, not
    # assumed.  The only consumer of this file is macOS's own keychain, so the
    # modern default buys nothing; legacy (RC2-40 + SHA-1) is what it reads.
    run(['openssl', 'pkcs12', '-export', '-legacy', '-inkey', str(key), '-in', str(crt),
         '-name', CN, '-out', str(p12), '-passout', f'pass:{password}'])
    return key, crt, p12


def assert_legacy_mac(p12):
    """Refuse to ship a PKCS#12 whose MAC older `security import` cannot verify.

    Reading the file back with OpenSSL proves nothing here: OpenSSL 3 reads both
    formats happily, so `pkcs12 -in -noout` succeeds on exactly the file that
    fails on macOS.  Only the algorithm identifier in the DER tells them apart.
    """
    dump = run(['openssl', 'asn1parse', '-inform', 'DER', '-in', str(p12)])
    digests = {line.rsplit(':', 1)[-1].strip() for line in dump.splitlines()
               if line.rstrip().endswith((SHA1_MAC, SHA256_MAC))}
    if SHA256_MAC in digests:
        raise SystemExit(
            'PKCS#12 用了 SHA-256 MAC，macOS 14 的 security import 会报\n'
            '"MAC verification failed during PKCS12 import"（看起来像密码错，实际是格式）。\n'
            '导出时必须带 -legacy。')
    if SHA1_MAC not in digests:
        raise SystemExit(f'PKCS#12 里找不到 SHA-1 MAC，需要人工确认:\n{dump}')
    print('p12 MAC: SHA-1（macOS 可读）')


def verify(crt):
    """Prove the extension that decides whether codesign will use this identity.

    Ask for the EKU *alone*.  `openssl x509` honours only the last `-ext` it is
    given, and asking with `-subject` too would make the check vacuous: the CN
    is "...Self-Signed Code Signing", so the phrase "Code Signing" is present in
    the subject line whether or not the extension exists.
    """
    eku = run(['openssl', 'x509', '-in', str(crt), '-noout', '-ext', 'extendedKeyUsage'])
    if 'Code Signing' not in eku:
        raise SystemExit(f'证书缺少 codeSigning 用途，codesign 不会认它:\n{eku}')
    print(eku.strip())
    # Not asserted: basicConstraints=CA:FALSE is the default here, but CA:TRUE is
    # the documented workaround if find-identity ever refuses to list it, so this
    # is informative rather than a gate.
    print(run(['openssl', 'x509', '-in', str(crt), '-noout', '-ext', 'basicConstraints']).strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--force', action='store_true',
                        help='覆盖已有证书。换证书 = 所有已授权用户重新授权一遍。')
    options = parser.parse_args()

    # Git Bash is UTF-8; without this the Chinese lines come out as mojibake.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'codesign.p12').exists() and not options.force:
        raise SystemExit(
            f'{OUT / "codesign.p12"} 已存在，没有覆盖。\n'
            '换掉证书意味着所有已经授权过的用户都要重新授权一次屏幕录制和输入监控。\n'
            '确实要重做请显式加 --force。')

    check_openssl()
    # Alphanumeric only: this password travels through `security import -P`,
    # GitHub secret storage and a YAML file, so punctuation is pure risk.
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    print('生成证书...')
    key, crt, p12 = generate(password)
    verify(crt)
    assert_legacy_mac(p12)

    blob = base64.b64encode(p12.read_bytes()).decode('ascii')
    (OUT / 'codesign.p12.b64.txt').write_text(blob + '\n', encoding='ascii')

    # The plaintext key has served its purpose; leaving it on disk is one more
    # copy to leak.
    key.unlink()
    assert not key.exists(), key
    assert p12.stat().st_size > 0

    (OUT / '凭据-请立即备份.txt').write_text(
        f'CN（绝对不能改）: {CN}\n'
        f'{P12_PASSWORD_SECRET}: {password}\n\n'
        f'要备份的文件: {p12}\n'
        f'还有: {OUT / "codesign.crt"}\n\n'
        '丢了私钥只是要重新配一次 CI；只要新证书的 CN 一模一样，\n'
        '用户的授权仍然有效（DR 里没有任何密钥材料）。\n'
        '但**不要改 CN** —— 改 CN 等于所有用户重新授权一遍。\n',
        encoding='utf-8')

    print()
    print('=' * 72)
    print('接下来把这两条加进 GitHub 仓库:')
    print('  Settings -> Secrets and variables -> Actions -> New repository secret')
    print()
    print(f'  名称: {P12_SECRET}')
    print('  值  : 下面这个文件里的全部内容（很长的一行，整行复制）')
    print(f'        {OUT / "codesign.p12.b64.txt"}')
    print()
    print(f'  名称: {P12_PASSWORD_SECRET}')
    print(f'  值  : {password}')
    print('=' * 72)
    print()
    print(f'私钥备份: 把整个 {OUT} 目录复制到密码管理器或 U 盘。')
    print('它不在版本库里（out/ 已被 .gitignore 忽略，另加了 *.p12 等规则）。')


if __name__ == '__main__':
    main()
