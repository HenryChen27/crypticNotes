"""Current raw overlay timing and process working set, local samples only."""
import json
from pathlib import Path
import time
import platform
import cv2
import numpy as np
import psutil
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.reference import read_image
from mapmatching.src.live import raw_layer,composite,presentation_candidate


def main():
    cv2.setNumThreads(1)
    root=Path(__file__).resolve().parents[2]
    out=root/'out/mapmatching/ui_showcase'
    out.mkdir(parents=True,exist_ok=True)
    process=psutil.Process()
    start=time.perf_counter()
    matcher=MapMatcher(root/'maps',difficulty='hard')
    index_ms=(time.perf_counter()-start)*1000
    samples=json.loads((root/'out/mapmatching/known_hard_layout.json').read_text(encoding='utf-8'))['samples']
    rows=[]
    tiles=[]
    for i,sample in enumerate(samples):
        start=time.perf_counter()
        cpu=process.cpu_times()
        pixels=read_image(root/sample['screenshot'])
        decoded=time.perf_counter()
        result=matcher.match(pixels)
        matched=time.perf_counter()
        candidate,message=presentation_candidate(result)
        if candidate is None:
            raise RuntimeError(message)
        reference=next(r for r in matcher.references if r.map_id==candidate.map_id)
        layer=raw_layer(pixels.shape,read_image(root/reference.source),reference,candidate)
        rendered=time.perf_counter()
        cpu_end=process.cpu_times()
        rows.append(dict(screenshot=sample['screenshot'],decode_ms=(decoded-start)*1000,match_ms=(matched-decoded)*1000,
                         source_decode_and_warp_ms=(rendered-matched)*1000,total_ms=(rendered-start)*1000,
                         cpu_ms=(cpu_end.user+cpu_end.system-cpu.user-cpu.system)*1000,
                         rss_mb=process.memory_info().rss/1024**2,peak_rss_mb=process.memory_info().peak_wset/1024**2))
        after=composite(pixels,layer)
        cv2.imencode('.png',after)[1].tofile(out/f'example_{i}_original_30.png')
        tile=np.hstack([cv2.resize(pixels,(640,400)),cv2.resize(after,(640,400))])
        cv2.putText(tile,f'Example {i} | Original screenshot / Source map at 30%',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
        tiles.append(tile)
    cv2.imencode('.jpg',np.vstack(tiles))[1].tofile(out/'all_examples_original_30.jpg')
    results=dict(environment=dict(python=platform.python_version(),logical_cpus=psutil.cpu_count(),threads=1),index_load_ms=index_ms,
                 median_match_ms=float(np.median([r['match_ms'] for r in rows])),median_decode_match_warp_ms=float(np.median([r['total_ms'] for r in rows])),
                 p95_decode_match_warp_ms=float(np.percentile([r['total_ms'] for r in rows],95)),samples=rows,
                 note='Warm OS file cache; excludes UI, capture, map opening animation and process import. Peak includes benchmark PNGs and contact sheet, not idle UI.')
    (out/'performance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=[]
    for i,sample in enumerate(samples):
        original='../../../'+sample['screenshot']
        cards.append(f'''<article><h2>Example {i}</h2><div class="compare"><img src="{original}"><img class="after" src="example_{i}_original_30.png"></div><input aria-label="Example {i} 对比位置" type="range" min="0" max="100" value="50" oninput="this.previousElementSibling.lastElementChild.style.clipPath='inset(0 0 0 '+this.value+'%)'"><p>左侧原截图 · 右侧原图 30% 叠加 · 拖动滑条对比</p><a href="example_{i}_original_30.png">打开完整叠图</a></article>''')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>加页手记 · 原图叠加展示</title><style>body{margin:40px auto;max-width:1180px;padding:0 20px;background:#191e20;color:#dcd1b8;font-family:system-ui}a{color:#cfba80}h1{font-weight:400}article{margin:32px 0;padding:18px;border:1px solid #635e4e;border-radius:10px;background:#242928}.compare{position:relative}.compare img{width:100%;display:block}.compare .after{position:absolute;inset:0;clip-path:inset(0 0 0 50%)}input{width:100%;accent-color:#c5b284}p{color:#b0aa9e}.ui{max-height:600px;max-width:100%}</style><h1>加页手记 · 悬浮地图助手</h1><p>原始地图颜色，不透明度 30%。这 6 张均由截图重新匹配后渲染，没有使用配对答案修正位置。当前为试用候选；困难模式已测试，噩梦暂不叠图。</p><p><a href="window/panel.png">真实界面截图</a> · <a href="performance.json">性能数据</a> · <a href="integration.json">Windows 集成测试</a></p><img class="ui" src="window/panel.png">'''+''.join(cards)+'</html>'
    (out/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(results,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
