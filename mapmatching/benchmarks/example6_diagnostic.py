"""Compare unmodified evidence with a diagnostic panel exclusion, no GT pose."""
from pathlib import Path
import json
import cv2
import numpy as np
from mapmatching.src.reference import load,read_image
from mapmatching.src.evidence import extract
from mapmatching.src.retrieval import retrieve
from mapmatching.src.registration import register
from dataclasses import asdict
from mapmatching.src.occlusion import control_panels
from mapmatching.src.live import raw_layer,composite


def main():
    cv2.setNumThreads(1)
    root=Path(__file__).resolve().parents[2]
    out=root/'out/mapmatching/example6_diagnostic'
    out.mkdir(parents=True,exist_ok=True)
    refs=load(root/'maps',difficulty='hard')
    results=[]
    for i,path in enumerate(sorted((root/'examples/6').glob('*.png'))):
        pixels=read_image(path)
        h,w=pixels.shape[:2]
        small=cv2.resize(pixels,(1000,round(h*1000/w)))
        automatic=(np.array(control_panels(small))*w/1000).round().astype(int).tolist()
        print('automatic boxes:',automatic)
        for mode,boxes in [('raw',None),('panel_excluded',automatic),('panel_and_soft_edges',None)]:
            ev=extract(pixels,exclude_regions=boxes,screenshot_cleanup=mode=='panel_and_soft_edges')
            ranked=retrieve(ev,refs)
            cs=sorted([register(ev,r) for r in ranked[:5]],key=lambda c:-(c.explained or 0))
            debug=cv2.resize(pixels,(ev.mask.shape[1],ev.mask.shape[0]))
            debug[ev.mask>0]=(0,220,255)
            cv2.imencode('.png',debug)[1].tofile(out/f'{i}_{mode}.png')
            row=dict(source=path.name,mode=mode,candidates=[asdict(c) for c in cs],diagnostics=ev.diagnostics)
            results.append(row)
            print(json.dumps(row,ensure_ascii=True))
            if mode=='panel_and_soft_edges':
                candidate=cs[0]
                ref=next(r for r in refs if r.map_id==candidate.map_id)
                layer=raw_layer(pixels.shape,read_image(root/ref.source),ref,candidate,ev.diagnostics['excluded_panel_boxes'])
                cv2.imencode('.png',composite(pixels,layer))[1].tofile(out/f'example6_{i}_fixed_overlay.png')
    (out/'comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
