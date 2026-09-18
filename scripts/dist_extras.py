"""把协作者侧的更新入口注入成品目录，并守住它们的编码。

`更新.cmd` 和 `update-client.ps1` 的**源**在 `scripts/` 下；成品目录（`dist/`）
每次打包都会被清空，所以这两个文件必须由脚本在每一关重新拷进去，不能手改成品里
的副本。这个模块就是那次拷贝的唯一实现 —— 打包（`finalize_release.py`）和分发
（`publish_dist.sh`）都调它。两边各写一份迟早会漂移，而漂移的后果是协作者双击
没反应、本地却完全看不出来。

注入必须在**压缩之前**发生，否则 zip 里没有 `更新.cmd`，从 Releases 下载的
协作者就没有更新按钮。

两条编码约束都是踩过坑的，在这里变成硬性检查：

  * `更新.cmd` 必须**纯 ASCII**。cmd.exe 按字节偏移定位批处理文件的下一行，
    文件里混入 GBK 中文会让偏移算错、从某一行中间开始执行（实测
    `where git >nul 2>nul` 被从 `ul` 处截断，报「命令语法不正确」）。
  * `update-client.ps1` 必须 **UTF-8 with BOM**。PowerShell 5.1 没有 BOM 就按
    控制台代码页（简体中文机器上是 GBK）读，中文全变乱码。

命令行用法（给 publish_dist.sh 用）：

    python scripts/dist_extras.py <成品目录>
"""
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent

# (scripts/ 下的源文件, 成品目录里的相对路径)
PAYLOAD = (
    ('更新.cmd', '更新.cmd'),
    ('update-client.ps1', 'scripts/update-client.ps1'),
)


def _check_line_endings(name, data):
    if b'\n' in data.replace(b'\r\n', b''):
        raise SystemExit(f'{name} 里出现了单独的 LF 行尾，Windows 上必须是 CRLF。')


def _validate(name, data):
    if name.endswith('.cmd'):
        bad = [b for b in data if b > 0x7F]
        if bad:
            raise SystemExit(
                f'{name} 里有非 ASCII 字节（首个 0x{bad[0]:02x}）。'
                'cmd.exe 按字节偏移定位批处理文件的下一行，混入中文会让它从行中间开始执行。'
                '中文请全部写到 update-client.ps1 里。')
        _check_line_endings(name, data)
    elif name.endswith('.ps1'):
        if not data.startswith(b'\xef\xbb\xbf'):
            raise SystemExit(
                f'{name} 丢了 UTF-8 BOM（开头是 {data[:3].hex() or "空文件"}）。'
                'PowerShell 5.1 没有 BOM 就按控制台代码页读，中文会全变乱码。')
        _check_line_endings(name, data)


def inject(product):
    """把两个更新入口拷进成品目录并校验编码，返回拷进去的相对路径。"""
    product = Path(product)
    if not product.is_dir():
        raise SystemExit(f'找不到成品目录 {product} —— 先跑一次打包。')
    written = []
    for source_name, relative in PAYLOAD:
        source = HERE / source_name
        if not source.is_file():
            raise SystemExit(f'找不到更新入口的源文件 {source}。')
        data = source.read_bytes()
        _validate(source_name, data)
        destination = product / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        written.append(relative)
    return written


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    for relative in inject(argv[1]):
        print(f'  注入 {relative}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
