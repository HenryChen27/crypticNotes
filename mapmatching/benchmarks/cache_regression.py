"""Warm single-map registration and genuine identity-change fallback."""
from pathlib import Path
import json
import time
import cv2
from mapmatching.src.reference import read_image
from mapmatching.src.matcher import MapMatcher
from mapmatching.src.live import match_with_cache


def main():
    cv2.setNumThreads(1)
    root=Path(__file__).resolve().parents[2]
    matcher=MapMatcher(root/'maps',difficulty='hard')
    sources=[root/'examples/0/example.png',root/'examples/3/example.png',root/'examples/6/example.png']
    cache=None
    rows=[]
    for path in sources:
        for attempt in range(2):
            pixels=read_image(path)
            start=time.perf_counter()
            result,candidate,message=match_with_cache(matcher,pixels,cache)
            ms=(time.perf_counter()-start)*1000
            assert candidate is not None,message
            if attempt==1:
                assert result.diagnostics['pipeline']=='cached_registration'
            elif cache is not None:
                assert result.diagnostics['pipeline']=='recognition_fallback'
            cache=candidate
            rows.append(dict(source=path.relative_to(root).as_posix(),attempt=attempt,map_id=candidate.map_id,
                             pipeline=result.diagnostics['pipeline'],ms=ms,pose=candidate.pose.__dict__))
    out=root/'out/mapmatching/example6_diagnostic/cache_regression.json'
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
