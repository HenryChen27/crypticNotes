"""Explicit, one-time installation of Microsoft's shared Evergreen runtime."""
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from PySide6 import QtCore as C


class EngineInstallTask(C.QThread):
    progress = C.Signal(int, str)
    result = C.Signal(str)

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix='minigame-webview-') as directory:
                installer = Path(directory)/'MicrosoftEdgeWebview2Setup.exe'
                request = urllib.request.Request('https://go.microsoft.com/fwlink/p/?LinkId=2124703')
                with urllib.request.urlopen(request, timeout=30) as source, installer.open('wb') as target:
                    received = 0
                    while block := source.read(65536):
                        if self.isInterruptionRequested():
                            raise InterruptedError('已取消安装')
                        received += len(block)
                        if received > 10*1024*1024:
                            raise ValueError('运行组件安装程序大小异常')
                        target.write(block)
                self.progress.emit(50, '正在验证微软签名…')
                # Never execute a downloaded bootstrapper without a valid Microsoft signature.
                escaped = str(installer).replace("'", "''")
                command = "$s=Get-AuthenticodeSignature -LiteralPath '"+escaped+"'; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { exit 1 }"
                flags = subprocess.CREATE_NO_WINDOW
                subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                               check=True, timeout=30, creationflags=flags, capture_output=True)
                if self.isInterruptionRequested():
                    raise InterruptedError('已取消安装')
                self.progress.emit(75, '正在安装，可能需要等待网络下载…')
                subprocess.run([str(installer), '/silent', '/install'], check=True, timeout=180, creationflags=flags)
            self.result.emit('')
        except Exception as error:
            self.result.emit('系统运行组件安装未完成：' + str(error))
