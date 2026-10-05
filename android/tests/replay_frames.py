"""Exercise the production Java comparator on the supplied phone screenshots."""
from pathlib import Path
import subprocess
import cv2
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/android-frame-replay'
OUT.mkdir(exist_ok=True)
for kind in ('open', 'closed'):
    for i in range(3):
        pixels = cv2.imread(str(ROOT / f'out/android-samples/{kind}-{i}.jpg'))
        if pixels is None:
            raise SystemExit('Missing phone samples')
        h, w = pixels.shape[:2]
        grid = pixels[(np.arange(90)*h//90)[:,None], np.arange(160)*w//160].astype(np.uint32)
        argb = (grid[:,:,2]<<16) | (grid[:,:,1]<<8) | grid[:,:,0]
        (OUT/f'{kind}-{i}.bin').write_bytes(argb.astype('>u4').tobytes())
JDK = ROOT/'out/android-tools/jdk/jdk-17.0.20.1+1/bin'
subprocess.run([str(JDK/'javac.exe'), '-d', str(OUT),
    str(ROOT/'android/app/src/main/java/com/crypticnotes/mobile/FrameEvidence.java'),
    str(ROOT/'android/tests/FrameEvidenceReplay.java')], check=True)
subprocess.run([str(JDK/'java.exe'), '-cp', str(OUT), 'com.crypticnotes.mobile.FrameEvidenceReplay', str(OUT)], check=True)
