"""Build a self-contained macOS application and ZIP on a real macOS runner."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
APP_NAME='加页手记'
BUNDLE_ID='com.henrychen.crypticnotes'
DIAGNOSTIC='诊断问题.command'

# Read big-endian, this one set covers thin and fat Mach-O in both byte orders,
# so no per-file endianness sniffing is needed and `file(1)` is not required.
MACHO_MAGICS={0xfeedface,0xcefaedfe,0xfeedfacf,0xcffaedfe,
              0xcafebabe,0xbebafeca,0xcafebabf,0xbfbafeca}
NESTED_SUFFIXES=('.app','.framework','.xpc','.bundle')


def is_macho(path):
    try:
        with open(path,'rb') as stream:
            head=stream.read(4)
    except OSError:
        return False
    return len(head)==4 and int.from_bytes(head,'big') in MACHO_MAGICS


def signing_identity(keychain):
    """Return the CN of the code-signing certificate, or refuse to build.

    Deliberately NOT `find-identity -v`.  `-v` keeps only identities whose trust
    is already valid, and a freshly imported self-signed certificate reports
    CSSMERR_TP_NOT_TRUSTED until it is explicitly trusted.  With `-v` that reads
    as "0 valid identities found", the lookup quietly misses, and the build
    falls back to ad-hoc signing -- producing an archive that looks perfectly
    healthy while every user loses their permissions on the next update.
    """
    expected=os.environ['MACOS_SIGNING_IDENTITY']
    command=['security','find-identity','-p','codesigning']
    if keychain: command.append(keychain)
    result=subprocess.run(command,capture_output=True,text=True)
    if f'"{expected}"' in result.stdout:
        return expected
    raise SystemExit(
        f'钥匙串里找不到代码签名身份 "{expected}"。\n'
        f'  $ {" ".join(command)}\n{result.stdout.strip()}\n'
        '可能的原因：\n'
        '  1. 导入时漏了 security set-key-partition-list（certificate/private key 没配上对）；\n'
        '  2. 证书缺少 extendedKeyUsage=codeSigning；\n'
        '  3. 证书是 CA:FALSE 且系统拒绝，改用 basicConstraints=critical,CA:TRUE 重新生成。\n'
        '不会退回 ad-hoc 签名：那会让用户每次更新都重新授权一次。')


def codesign(path,identity,keychain,identifier=None):
    # --force because PyInstaller already ad-hoc signed everything, and
    # --timestamp=none because Apple's timestamp server will not stamp a
    # self-signed certificate (the default would fail or hang).
    command=['/usr/bin/codesign','--force','--sign',identity,'--timestamp=none']
    if keychain: command+=['--keychain',keychain]
    if identifier: command+=['--identifier',identifier]
    command.append(str(path))
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        raise SystemExit(f'codesign 失败 ({path}):\n{result.stderr.strip()}')


def sign(app,identity,keychain):
    """Sign inside out: nested code first, the bundle last.

    `--deep` is a *verification* flag that Apple deprecated for signing.  On a
    PyInstaller --onedir bundle -- a flat pile of .so/.dylib under
    Contents/Frameworks plus the bootloader -- it signs nested code in an
    unspecified order and can miss Mach-O files it does not classify as code.

    Hardened runtime (--options runtime) and entitlements are deliberately NOT
    used: hardened runtime turns on library validation, which requires every
    loaded library to carry the same Team ID, and a self-signed certificate has
    no Team ID at all.  It is also a prerequisite for notarization, not a
    Gatekeeper bypass, so without a Developer ID it buys nothing and only adds
    ways for the app to fail to launch.
    """
    binaries=[]; bundles=[]
    for root,dirs,files in os.walk(app,followlinks=False):
        dirs[:]=[name for name in dirs
                 if name!='_CodeSignature' and not os.path.islink(os.path.join(root,name))]
        if Path(root)!=app and Path(root).name.endswith(NESTED_SUFFIXES):
            bundles.append(Path(root))
        for name in files:
            path=Path(root)/name
            if not path.is_symlink() and is_macho(path):
                binaries.append(path)
    deepest=lambda path: len(path.parts)
    binaries.sort(key=deepest,reverse=True)
    bundles.sort(key=deepest,reverse=True)
    for path in binaries: codesign(path,identity,keychain)
    for path in bundles: codesign(path,identity,keychain)
    codesign(app,identity,keychain,identifier=BUNDLE_ID)
    print(f'已签名: {len(binaries)} 个 Mach-O、{len(bundles)} 个嵌套 bundle、1 个 .app')


def verify(app,identity):
    """Prove the designated requirement is the stable form, and fail the build if not.

    This is the assertion that catches an ad-hoc fallback.  An ad-hoc bundle's
    DR reads `identifier "..." and cdhash H"..."`, which pins a hash that
    changes on every build -- exactly the bug this signing exists to fix.
    """
    result=subprocess.run(['/usr/bin/codesign','-d','-r-','--verbose=4',str(app)],
                          capture_output=True,text=True)
    # codesign splits this across both streams: the verbose dump goes to stderr,
    # the requirement itself to stdout.  Reading only stderr finds no
    # `designated =>` line at all -- which is indistinguishable from an unsigned
    # bundle, so the check has to see the concatenation.
    stdout,stderr=result.stdout,result.stderr
    # Printed unconditionally: a release should leave a permanent record of the
    # requirement its users' permissions are bound to.
    print(stdout.strip())
    print(stderr.strip())
    text=stdout+'\n'+stderr
    line=next((l for l in text.splitlines() if 'designated =>' in l),None)
    if line is None:
        raise SystemExit(
            '读不出指定要求(DR)：codesign 的两个输出流里都没有 designated => 行。\n'
            f'--- stdout ---\n{stdout.strip()}\n--- stderr ---\n{stderr.strip()}')
    dr=line.split('designated =>',1)[1].strip()
    if not (f'identifier "{BUNDLE_ID}"' in dr
            and ('certificate leaf[subject.CN]' in dr or 'certificate root[subject.CN]' in dr)
            and f'"{identity}"' in dr
            and 'cdhash' not in dr):
        raise SystemExit(
            '签名后的 DR 不是稳定形态，TCC 授权仍会在每次更新后丢失。\n'
            f'  实际: {dr}\n'
            '看到 cdhash 就说明回落到了 ad-hoc 签名。若形态不同但确实绑在证书上，\n'
            '把上面这行 DR 原样贴回来，按实际形态放宽这里的判定。')
    if '(runtime)' in text:
        raise SystemExit('签名带上了 hardened runtime；自签名证书没有 Team ID，会拖垮启动。')
    check=subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict','--verbose=2',str(app)],
                         capture_output=True,text=True)
    if check.returncode or 'Signature=adhoc' in check.stdout+check.stderr:
        raise SystemExit(f'签名校验失败:\n{check.stdout.strip()}\n{check.stderr.strip()}')
    print(f'签名自检通过，DR 与 "{identity}" 绑定。')


def main():
    # The refusal messages below are Chinese and are the point of the guard;
    # without this they are mojibake on a Windows console.  No-op on the runner.
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    app=ROOT/'dist-macos'/f'{APP_NAME}.app'
    skip=bool(os.environ.get('MACOS_SKIP_SIGNING'))
    identity=os.environ.get('MACOS_SIGNING_IDENTITY','').strip()
    # Fail before the expensive build rather than after it.
    if not skip and not identity:
        raise SystemExit(
            'MACOS_SIGNING_IDENTITY 未设置，拒绝构建未签名的 macOS 包。\n'
            'ad-hoc 签名的 DR 会钉住 cdhash，用户每次更新都要重新授权屏幕录制和输入监控。\n'
            'CI 里由工作流的 "Import signing certificate" 步骤设置这个变量。\n'
            '确实要构建未签名版本（仅本地排查）请显式设 MACOS_SKIP_SIGNING=1。')

    subprocess.run([sys.executable,'-m','mapmatching','build-index','--index',str(ROOT/'maps')],
                   cwd=ROOT,check=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir',
          '--name',APP_NAME,'--paths',str(ROOT),
          '--hidden-import','mapmatching.portable_check',
          '--hidden-import','ScreenCaptureKit',
          '--osx-bundle-identifier',BUNDLE_ID,
          '--distpath',str(ROOT/'dist-macos'),'--workpath',str(ROOT/'build/pyinstaller-macos'),
          '--specpath',str(ROOT/'build')]
    for module in ('torch','tensorflow','matplotlib','pandas','IPython','pytest','notebook','tkinter','win32gui','win32api','win32ui','win32con'):
        args += ['--exclude-module',module]
    data=[ROOT/'mapmatching/assets',ROOT/'docs/images',
          *(ROOT/'maps'/name for name in ('hard','nightmare','_unindexed','evidence','floors.json','index.json','disabled.json','README.md')),
          ROOT/'README.md']
    data.extend(p for p in (ROOT/'mapmatching/appearance/skins').rglob('*')
                if p.is_file() and p.suffix.lower() in ('.png','.jpg','.webp','.json'))
    data.extend((ROOT/'mapmatching').glob('*.md'))
    for path in data:
        if path.exists():
            destination=path.relative_to(ROOT) if path.is_dir() else path.parent.relative_to(ROOT)
            args += ['--add-data',f'{path}{os.pathsep}{destination}']
    args.append(str(ROOT/'mapmatching/launch.py'))
    subprocess.run(args,cwd=ROOT,check=True)

    if not app.is_dir():
        raise SystemExit(f'App bundle not generated: {app}')

    if skip:
        print('!'*72)
        print('!! 未签名构建：用户每次更新都要重新授权屏幕录制和输入监控 !!')
        print('!'*72)
    else:
        # Empty on a local Mac that imported into the login keychain; the runner
        # passes the temporary keychain it created.
        keychain=os.environ.get('MACOS_KEYCHAIN','').strip()
        identity=signing_identity(keychain)
        sign(app,identity,keychain)
        verify(app,identity)

    release=ROOT/'release'; release.mkdir(exist_ok=True)
    arch=os.environ.get('MACOS_ARCH','arm64')
    archive=release/f'IdentityVMapAssistant-macOS-{arch}.zip'
    if archive.exists(): archive.unlink()
    # The diagnostic has to sit *next to* the bundle, never inside it: adding a
    # file to a signed bundle breaks the seal and codesign --verify --strict
    # fails.  Zipping the directory rather than the .app with --keepParent puts
    # its contents at the archive root, so the .app stays where it was and the
    # README's "解压后拖入应用程序" still reads correctly.
    diagnostic=ROOT/'dist-macos'/DIAGNOSTIC
    shutil.copy2(ROOT/'scripts/diagnose_macos.command',diagnostic)
    os.chmod(diagnostic,0o755)
    entries=sorted(path.name for path in (ROOT/'dist-macos').iterdir())
    if entries!=[f'{APP_NAME}.app',DIAGNOSTIC]:
        raise SystemExit(f'dist-macos/ 内容不符合预期（--noconfirm 不会清理旧产物）: {entries}')
    # ditto preserves executable bits and the .app bundle layout, and is present
    # on every supported macOS runner.
    subprocess.run(['ditto','-c','-k','--sequesterRsrc',
                    str(ROOT/'dist-macos'),str(archive)],check=True)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (release/f'macos-{arch}-SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(f'macOS ZIP: {archive.stat().st_size/1024**2:.1f} MiB')


if __name__=='__main__': main()
