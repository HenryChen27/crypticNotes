"""Detect stacked rectangular control panels already baked into screenshots."""
import cv2
import numpy as np


def control_panels(bgr):
    h,w=bgr.shape[:2]
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    bright=((hsv[:,:,2]>=100)&(hsv[:,:,1]<=100)).astype(np.uint8)
    bright=cv2.morphologyEx(bright,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(bright,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if .04*w<=bw<=.30*w and .018*h<=bh<=.08*h and 2<=bw/bh<=12 and cv2.contourArea(contour)/(bw*bh)>.82:
            boxes.append((x,y,bw,bh))
    panels=[]
    for x,y,bw,bh in boxes:
        # Several controls aligned down a column, spanning a substantial height.
        # A single rectangular room is not sufficient evidence for UI exclusion.
        column=[b for b in boxes if abs(b[0]-x)<=.015*w and .45*bw<=b[2]<=2.2*bw]
        if len(column)<3 or max(b[1] for b in column)-min(b[1] for b in column)<.15*h:
            continue
        left=min(b[0] for b in column)
        right=max(b[0]+b[2] for b in column)
        top=min(b[1] for b in column)
        bottom=max(b[1]+b[3] for b in column)
        box=[max(0,int(left-.015*w)),max(0,int(top-.18*h)),min(w,int(right+.015*w)),min(h,int(bottom+.025*h))]
        if box not in panels:
            panels.append(box)
    return panels


def sharp_boundary(bgr,boundary):
    """Reject weak fog silhouettes; keep visible wall edges near the mask."""
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)/8
    gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)/8
    strength=cv2.dilate(cv2.magnitude(gx,gy),np.ones((3,3),np.uint8))
    return boundary*(strength>=8).astype(np.uint8)
