"""Packaged startup/resource/multiprocessing smoke, without global hotkeys."""
import json
import multiprocessing as mp
from pathlib import Path
import time
import cv2
import numpy as np
from .paths import ROOT,DATA_ROOT
from .src.reference import load,read_image
from .src.live import worker


def run(output):
    from .ui import W,font_stack
    app=W.QApplication([]); fonts=font_stack()
    references=load(ROOT/'maps')
    ref=next(r for r in references if r.map_id=='hard/北-T门')
    original=read_image(ROOT/ref.source)
    x,y,X,Y=ref.regions[0]['bbox']
    scale=min(1000/(X-x),530/(Y-y))
    source=np.zeros_like(original);source[y:Y,x:X]=original[y:Y,x:X]
    screen=cv2.warpAffine(source,np.array([[scale,0,1100-scale*(x+X)/2],[0,scale,540-scale*(y+Y)/2]]),(1920,1080))
    parent,child=mp.Pipe()
    process=mp.Process(target=worker,args=(child,str(ROOT),'hard',None))
    process.start(); child.close()
    try:
        assert parent.poll(45),'worker startup timeout'
        kind,payload=parent.recv(); assert kind=='ready',(kind,payload)
        parent.send((1,screen,None))
        assert parent.poll(30),'matching timeout'
        kind,payload=parent.recv(); assert kind=='result',(kind,str(payload))
        _,layer,message,candidate,elapsed,_=payload
        assert layer is not None and candidate.map_id==ref.map_id,(message,candidate)
        report=dict(ok=True,reference_count=len(references),fonts=fonts,map_id=candidate.map_id,
                    processing_ms=elapsed,layer_shape=list(layer.shape),data_root=str(DATA_ROOT))
        Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        parent.send(None)
        process.join(5)
        if process.is_alive():process.terminate();process.join()
        parent.close();process.close()

