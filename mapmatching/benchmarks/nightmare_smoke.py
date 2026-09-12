"""Synthetic source-derived checks, NOT a real-game accuracy benchmark."""
from pathlib import Path
import json
import cv2
import numpy as np
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.reference import read_image
from mapmatching.src.live import presentation_candidate,raw_layer,composite


def main():
    cv2.setNumThreads(1); cv2.setRNGSeed(0)
    root=Path(__file__).resolve().parents[2]
    out=root/'out/mapmatching/nightmare_validation'; out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for mode in ('solo','duo'):
        matcher=MapMatcher(root/'maps',difficulty='nightmare',mode=mode)
        for ref in matcher.references:
            original=read_image(root/ref.source)
            for region in ref.regions:
                x,y,X,Y=region['bbox']
                scale=min(1000/(X-x),530/(Y-y))
                tx=1100-scale*(x+X)/2; ty=540-scale*(y+Y)/2
                source=np.zeros_like(original); source[y:Y,x:X]=original[y:Y,x:X]
                screen=cv2.warpAffine(source,np.array([[scale,0,tx],[0,scale,ty]]),(1920,1080))
                result=matcher.match(screen)
                chosen,message=presentation_candidate(result)
                best=result.candidates[0] if result.candidates else None
                error=None
                if best and best.pose and best.map_id==ref.map_id:
                    p=best.pose
                    corners=np.array([[x,y],[X,Y],[x,Y],[X,y]])
                    error=float(np.linalg.norm(corners*(p.scale-scale)+[p.tx-tx,p.ty-ty],axis=1).max())
                row=dict(map_id=ref.map_id,floor=region['floor'],candidate=best.map_id if best else None,
                         candidate_floor=best.floor if best else None,displayed=chosen is not None,
                         max_corner_error_px=error,message=message)
                rows.append(row)
                if chosen and chosen.map_id==ref.map_id and ref==matcher.references[0]:
                    layer=raw_layer(screen.shape,original,ref,chosen)
                    cv2.imwrite(str(out/f'{mode}_{region["floor"]}.png'),composite(screen,layer))
        print(mode,'completed',flush=True)
    report=dict(kind='synthetic source-derived smoke only; no real-game accuracy claim',
                total=len(rows),correct_identity=sum(r['candidate']==r['map_id'] for r in rows),
                correct_floor=sum(r['candidate']==r['map_id'] and r['candidate_floor']==r['floor'] for r in rows),
                displayed=sum(r['displayed'] for r in rows),rows=rows)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k!='rows'})


if __name__=='__main__':
    main()
