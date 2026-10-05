"""Gate must accept composited map frames without hiding the overlay."""
import sys
from pathlib import Path
import cv2
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'android/app/src/main/python'))
from mobile_gate import inspect_map_ui
count=0
for kind in ('open','closed'):
    for i in range(3):
        original=cv2.imread(str(root/f'out/android-samples/{kind}-{i}.jpg'))
        h,w=original.shape[:2]
        for bounds in ((.195,.01,.395,.1),(.87,.02,.99,.15)):
            frame=original.copy()
            # Simulate our alpha layer; it is clipped to this viewport.
            if kind=='open':
                roi=frame[int(.12*h):int(.87*h),int(.41*w):int(.86*w)]
                roi[:]=cv2.convertScaleAbs(roi,alpha=.7,beta=65)
            a,b,A,B=bounds
            frame[int(b*h):int(B*h),int(a*w):int(A*w)]=0
            result=inspect_map_ui(frame,bounds)
            assert result['visible']==(kind=='open'),(kind,i,bounds,result)
            count+=1
print('PASS',count,'composited/occluded gate checks')
