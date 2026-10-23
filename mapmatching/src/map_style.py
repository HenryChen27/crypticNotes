"""Reference-only author styles. Screenshot extraction remains unchanged."""
import cv2
import numpy as np


def zhanshi_mask(image):
    """Recover terrain, excluding vivid route strokes and gray watermarks.

    Work at a fixed atlas resolution so JPEG dimensions do not change cleanup.
    Fill annotation holes only when their pixels contain a vivid colored mark;
    black courtyards remain negative space.
    """
    h,w=image.shape[:2]
    small=cv2.resize(image,(1000,round(h*1000/w)),interpolation=cv2.INTER_AREA)
    hue,sat,val=cv2.split(cv2.cvtColor(small,cv2.COLOR_BGR2HSV))
    terrain=(((hue>=85)&(hue<=120)&(sat>35)&(sat<195)&(val>85)) |
             ((hue<18)&(sat>45)&(sat<170)&(val>110))).astype(np.uint8)
    terrain=cv2.morphologyEx(terrain,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(1-terrain,8)
    vivid=(sat>195)&(val>150)
    for i in range(1,n):
        x,y,cw,ch,area=stats[i]
        if x==0 or y==0 or x+cw==terrain.shape[1] or y+ch==terrain.shape[0]:continue
        hole=labels[y:y+ch,x:x+cw]==i
        if area<1200 and np.mean(vivid[y:y+ch,x:x+cw][hole])>.30:
            terrain[y:y+ch,x:x+cw][hole]=1
    n,labels,stats,_=cv2.connectedComponentsWithStats(terrain,8)
    keep=np.flatnonzero(stats[:,cv2.CC_STAT_AREA]>=80)
    return np.isin(labels,keep[keep!=0]).astype(np.uint8)


def floor_selection(shape,region,factor=1.):
    """A polygon union prevents adjacent atlas floors leaking through a box."""
    selected=np.zeros(shape[:2],np.uint8)
    polygons=region.get('polygons')
    if polygons:
        cv2.fillPoly(selected,[np.rint(np.asarray(p)*factor).astype(np.int32) for p in polygons],1)
    else:
        x,y,X,Y=np.rint(np.asarray(region['bbox'])*factor).astype(int)
        selected[max(0,y):max(0,Y),max(0,x):max(0,X)]=1
    return selected
