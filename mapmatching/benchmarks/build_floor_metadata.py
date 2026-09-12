"""已停用：一次性工具，产物已经躺进 `maps/floors.json`。

它当年做的事是「把 `floor_probe.json` 的探针结果 + 人工复核的插图修正，
合成 `mapmatching/reference/floor_regions.json`」。现在没有那个文件了：
登记表就是 `maps/floors.json`，而它的 Hard 条目正是由
`scripts/migrate_maps.py` 从同一个 `floor_regions.json` 搬过来的
（`review` 字段逐字相同，`source_sha256` 换成了 `sha256`）。

**为什么不做成「写 maps/floors.json」**：
1. `migrate_maps.py` 是刻意只跑一次的（目标存在就拒绝覆盖），迁移已经完成；
2. 新版条目的 `name` / `pixel_sha256` 是这里不产出、但 UI 和查重都要用的字段，
   重跑一遍会把它们抹掉；schema 也会从 2 退回 1；
3. 它的输入 `out/mapmatching/floor_probe.json` 只是评测中间产物，
   不该再成为登记表的真源 —— `floors.json` 现在是用户数据，由录入/移除流程维护。

所以保留文件、改成显式的 no-op，避免有人照着旧文档再跑一次把登记表写坏。
"""
import sys

# 控制台是 UTF-8，但 Python 默认按 cp936 编码输出，中文会变成乱码。
sys.stdout.reconfigure(encoding='utf-8')


def main() -> None:
    # 走 stdout 而不是 SystemExit(str)：后者写 stderr，而 stderr 不在上面 reconfigure
    # 的范围内，中文会以 cp936 输出成乱码。
    print('build_floor_metadata 已停用（no-op）：不再改写任何文件。\n'
          'Hard 楼层几何当年由它合成 reference/floor_regions.json，那些条目现在已经是 '
          'maps/floors.json 里的登记条目（搬迁见 scripts/migrate_maps.py）。\n'
          '要改某张图的楼层几何，请走 UI 的「管理地图 / 新增地图」，或直接改 maps/floors.json '
          '后再用 python -m mapmatching build-index 重建特征。')


if __name__ == '__main__':
    main()
