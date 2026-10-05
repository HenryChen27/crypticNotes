package com.crypticnotes.mobile;

/** Pixel-grid comparison independent of Android; shared by capture and replay tests. */
final class FrameEvidence {
    static int changes(int[] a, int[] b, int x0, int y0, int x1, int y1, int threshold,
                       int excludedLeft, int excludedTop, int excludedRight, int excludedBottom) {
        int changed = 0;
        for (int y=y0; y<y1; y++) for (int x=x0; x<x1; x++) {
            if (x>=excludedLeft && x<=excludedRight && y>=excludedTop && y<=excludedBottom) continue;
            int p=a[y*160+x], q=b[y*160+x];
            if (Math.abs((p>>16&255)-(q>>16&255)) + Math.abs((p>>8&255)-(q>>8&255))
                    + Math.abs((p&255)-(q&255)) > threshold) changed++;
        }
        return changed;
    }
}
