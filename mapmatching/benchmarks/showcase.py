"""Build actual inference-driven previews. GT is attached only AFTER rendering."""
from __future__ import annotations
from pathlib import Path
import html
import json
import cv2
import numpy as np
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.reference import read_image
from mapmatching.src.preview import render_preview
from mapmatching.src.evidence import extract


def write_image(path: Path, pixels: np.ndarray) -> None:
    cv2.imencode(path.suffix, pixels)[1].tofile(path)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root/'out/mapmatching/showcase'
    out.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    matcher = MapMatcher(root/'maps', difficulty='hard')
    refs = {r.map_id:r for r in matcher.references}
    evaluation = json.loads((root/'out/mapmatching/known_hard_layout.json').read_text(encoding='utf-8'))
    pose_eval = json.loads((root/'out/mapmatching/pose_layout.json').read_text(encoding='utf-8'))
    rows, cards, contact = [], [], []
    for i, item in enumerate(evaluation['samples']):
        screenshot = read_image(root/item['screenshot'])
        # Match only pixels with the explicit user-supplied difficulty.
        result = matcher.match(screenshot)
        candidate = result.candidates[0]
        ref = refs[candidate.map_id]
        overlay, metadata = render_preview(screenshot, read_image(root/ref.source), ref, candidate)
        write_image(out/f'example_{i}_overlay.png', overlay)
        ev = extract(screenshot)
        _,_,stats,_ = cv2.connectedComponentsWithStats(ev.mask,8)
        x,y,w,h = stats[1:][np.argmax(stats[1:,cv2.CC_STAT_AREA])][:4]
        x0,y0 = np.floor(np.array([x-14,y-14])/ev.image_factor).astype(int)
        x1,y1 = np.ceil(np.array([x+w+14,y+h+14])/ev.image_factor).astype(int)
        x0,y0,x1,y1 = max(0,x0),max(0,y0),min(screenshot.shape[1],x1),min(screenshot.shape[0],y1)
        before, after = screenshot[y0:y1,x0:x1], overlay[y0:y1,x0:x1]
        write_image(out/f'example_{i}_before_detail.png', before)
        write_image(out/f'example_{i}_after_detail.png', after)
        tiles = []
        for label,pic in [('Before',before),('After',after)]:
            factor = min(610/pic.shape[1],355/pic.shape[0])
            resized = cv2.resize(pic,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
            tile = np.full((400,640,3),(24,19,15),np.uint8)
            yy,xx = 38+(355-resized.shape[0])//2,(640-resized.shape[1])//2
            tile[yy:yy+resized.shape[0],xx:xx+resized.shape[1]] = resized
            cv2.putText(tile,f'Example {i} / {label}',(18,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(235,235,235),1,cv2.LINE_AA)
            tiles.append(tile)
        comparison = np.hstack(tiles)
        write_image(out/f'example_{i}_comparison.jpg',comparison)
        contact.append(comparison)
        error = next(r for r in pose_eval['samples'] if r['screenshot']==item['screenshot'])
        metadata.update({'screenshot':item['screenshot'],'inference_status':result.status,
                         'gt_map_evaluation_only':item['gt_map'],'map_correct':candidate.map_id==item['gt_map'],
                         'manual_reprojection_rmse_px':error['reprojection_rmse_px'],
                         'manual_annotation_quality':pose_eval['quality'],
                         'detail_crop_xyxy':[int(x0),int(y0),int(x1),int(y1)]})
        rows.append(metadata)
        name=html.escape(candidate.map_id)
        cards.append(f'''<section><header><h2>Example {i} · {name} · {candidate.floor}F</h2><span>对齐 RMS {error['reprojection_rmse_px']:.2f} px · 初步人工标注</span></header>
<div class="compare" id="c{i}"><img src="example_{i}_after_detail.png" alt="叠图后"><img class="before" src="example_{i}_before_detail.png" alt="原始局部"><div class="divider"></div></div>
<label>拖动对比：原图 ↔ 叠图 <input type="range" min="0" max="100" value="50" aria-label="Example {i} 原图与叠图对比" oninput="document.getElementById('c{i}').style.setProperty('--split',this.value+'%')"></label>
<p><a href="example_{i}_overlay.png">查看完整分辨率叠图</a> · <a href="example_{i}_comparison.jpg">查看并排对比图</a></p></section>''')
    write_image(out/'all_examples_comparison.jpg',np.vstack(contact))
    (out/'manifest.json').write_text(json.dumps({'difficulty':'hard','method':'fresh pixel-only inference; top candidate; no GT pose adjustment','results':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>加页手记 · 自动叠图展示</title><style>
*{box-sizing:border-box}body{background:#10191f;color:#e8eff2;font-family:system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:40px 24px}main{max-width:1140px;margin:auto}h1{font-size:34px;margin-bottom:12px}p{line-height:1.8;color:#bccbd2}.badge{display:inline-block;background:#193c42;color:#71e8db;border:1px solid #396567;border-radius:8px;padding:7px 12px}section{background:#19252e;border:1px solid #304451;border-radius:14px;padding:22px;margin:25px 0}header{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}h2{font-size:19px}span{color:#a9c1cc}.compare{--split:50%;position:relative;max-height:680px;width:100%;overflow:hidden;background:#0e171d}.compare>img{width:100%;display:block}.compare>img.before{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--split)) 0 0)}.divider{position:absolute;top:0;bottom:0;left:var(--split);border-left:2px solid #65e8e0}label{display:block;margin-top:15px}input{width:100%;accent-color:#61d9d3;margin-top:12px}a{color:#78dfeb}footer{color:#94aab8;font-size:14px;padding:20px 0}</style><main>
<div class="badge">困难模式 · 6 个原始 example · 自动识别与配准</div><h1>标准地图，叠到当前可见道路上</h1>
<p>青色线是标准地图结构，彩色线保留原图路线标记。每张图都重新运行像素匹配，未按人工答案挪动位置。拖动滑条，比较原图与叠图；打开完整图查看尚未探索区域的道路。</p>
<p>这是离线效果展示，尚未启用游戏内悬浮窗或可靠自动锁定。当前 6/6 识别正确只覆盖 4 张困难地图；像素误差来自带点选误差的初步人工标注。噩梦模式缺少实测截图。</p>'''+''.join(cards)+'''<footer>原始图坐标 → 完整截图坐标：u = s·x + tx，v = s·y + ty。楼层和插图通过独立 reference 布局元数据约束。<a href="manifest.json">查看逐图变换与检查记录</a></footer></main></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'examples':len(rows),'map_correct':sum(r['map_correct'] for r in rows),'outside_viewport_modified':sum(r['outside_viewport_changed_pixels'] for r in rows),'output':str(out)},ensure_ascii=True))


if __name__ == '__main__':
    main()
