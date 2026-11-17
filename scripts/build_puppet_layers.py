"""Cut the 守财木偶 artwork into the layers its rig plays back.

Unlike the doll and the lantern, this body cannot be split by polygons at
run time: the sack hangs over the shoulder in front of the shirt, so taking
it away leaves a hole that has to be painted in, and the far arm is hidden
behind the sack altogether. This script does that once and writes the result
to ``mapmatching/appearance/skins/puppet/layers``:

- the sack is recognised by its translucency in the source image (alpha well
  below the body's) plus a polygon for its opaque neck, knot and rope;
- the shirt under the knot is rebuilt by mirroring the chevron stripes about
  their apex;
- the far arm is a darkened mirror of the near one;
- alpha is raised so nothing reads as a ghost on a desktop.

Run it by hand after changing ``image.png``; nothing imports it.
"""
from pathlib import Path
import numpy as np
import cv2

SKIN = Path(__file__).resolve().parents[1]/'mapmatching/appearance/skins/puppet'
W, H = 444, 484
BODY_ALPHA = 172            # the sack's cloth never reaches this, the body always does
MIRROR_X = 206              # apex of the shirt's chevrons; the body is mirrored about it

# Left edge of the sack where it is opaque (neck, knot, the gripping hand,
# the rope) and so cannot be told from the body by alpha; closed on the right.
SACK = [(199, 104), (203, 150), (207, 183), (208, 212), (208, 247), (205, 262), (205, 286),
        (214, 294), (243, 297), (243, 336), (252, 348), (262, 362), (400, 362), (400, 96)]
# The part of the sack that passes in front of the shirt.
SACK_FRONT = [(199, 104), (203, 150), (207, 183), (208, 212), (208, 247), (205, 262), (205, 286),
              (214, 294), (243, 297), (286, 305), (290, 250), (262, 212), (240, 150), (232, 104)]

HEAD = [(84, 150), (150, 50), (215, 50), (205, 150), (208, 190), (208, 228), (202, 250),
        (166, 255), (140, 248), (112, 226), (100, 200), (84, 186)]
ARM_UPPER = [(138, 250), (166, 252), (168, 300), (140, 303)]
ARM_LOWER = [(140, 288), (166, 288), (163, 318), (150, 346), (142, 380), (104, 380), (106, 342), (130, 320)]
TORSO = [(150, 236), (252, 236), (252, 346), (262, 362), (226, 352), (216, 392), (196, 392),
         (192, 352), (150, 352), (166, 300), (166, 252)]
LEG_L_UPPER = [(158, 344), (196, 344), (198, 380), (158, 380)]
LEG_L_LOWER = [(156, 372), (198, 372), (198, 440), (140, 440), (140, 402), (160, 398)]
LEG_R_UPPER = [(218, 344), (254, 344), (258, 380), (218, 380)]
LEG_R_LOWER = [(218, 372), (258, 372), (270, 440), (212, 440), (214, 400)]


def polygon(points):
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [np.array(points, np.int32)], 255)
    return mask > 0


def save(name, rgba):
    target = SKIN/'layers'/(name+'.png')
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode('.png', rgba)[1].tofile(str(target))


def mirrored(layer):
    """Reflect a layer about MIRROR_X."""
    out = np.zeros_like(layer)
    xs = np.arange(W)
    source = 2*MIRROR_X-xs
    ok = (source >= 0) & (source < W)
    out[:, xs[ok]] = layer[:, source[ok]]
    return out


def main():
    image = cv2.imdecode(np.fromfile(str(SKIN/'image.png'), np.uint8), cv2.IMREAD_UNCHANGED)
    assert image.shape == (H, W, 4), image.shape
    alpha = image[..., 3]
    in_sack = polygon(SACK)
    core = (alpha >= BODY_ALPHA) & ~in_sack
    kernel = np.ones((3, 3), np.uint8)
    body = cv2.dilate(core.astype(np.uint8), kernel, iterations=2) > 0
    legs = polygon(LEG_L_UPPER) | polygon(LEG_L_LOWER) | polygon(LEG_R_UPPER) | polygon(LEG_R_LOWER)
    body = (body & ~in_sack) | (legs & (np.indices((H, W))[0] >= 352))
    body &= alpha > 0
    sack = (alpha > 0) & ~(cv2.dilate(core.astype(np.uint8), kernel, iterations=1) > 0)
    sack &= ~(legs & (np.indices((H, W))[0] >= 352))
    # Drop the hairline of antialiased body edge the alpha test leaves behind.
    sack = cv2.morphologyEx(sack.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0

    solid = image.copy()
    solid[..., 3] = np.clip(alpha.astype(np.float32)*1.7, 0, 255).astype(np.uint8)
    cloth = image.copy()
    cloth[..., 3] = np.clip(alpha.astype(np.float32)*2.1, 0, 240).astype(np.uint8)

    def cut(source, mask):
        layer = source.copy()
        layer[~mask] = 0
        return layer

    front = polygon(SACK_FRONT) & (alpha >= 150)
    full = whole_sack(cloth, sack)
    # Behind the body the whole sack is drawn, so a swing never opens a gap.
    save('sack', full)
    save('sack_front', cut(cloth, sack & front))

    head = polygon(HEAD) & body
    arm_upper = polygon(ARM_UPPER) & body & ~head
    arm_lower = polygon(ARM_LOWER) & body & ~head
    arm = arm_upper | arm_lower
    save('head', cut(solid, head))
    save('arm_upper', cut(solid, arm_upper))
    save('arm_lower', cut(solid, arm_lower & ~polygon([(138, 250), (166, 252), (167, 288), (139, 288)])))
    for name, points in (('leg_l_upper', LEG_L_UPPER), ('leg_l_lower', LEG_L_LOWER),
                         ('leg_r_upper', LEG_R_UPPER), ('leg_r_lower', LEG_R_LOWER)):
        mask = polygon(points) & body & (np.indices((H, W))[0] >= 350)
        if name.endswith('upper'):
            mask &= ~polygon([(196, 344), (218, 344), (218, 395), (196, 395)])
        save(name, cut(solid, mask))

    # Torso: what the polygon holds, then the half the sack covered, mirrored
    # from the visible half, then a neck stub so a tilting head opens no gap.
    torso_mask = polygon(TORSO) & body & ~arm & ~head
    rows = np.indices((H, W))[0]
    torso_mask &= ~(legs & (rows >= 352) & ~polygon([(192, 344), (222, 344), (222, 395), (192, 395)]))
    torso = cut(solid, torso_mask)
    reflected = mirrored(torso)
    fill = (reflected[..., 3] > 0) & (torso[..., 3] < 200) & (np.indices((H, W))[1] > MIRROR_X) & (rows < 300)
    shaded = reflected.copy()
    shaded[..., :3] = (shaded[..., :3].astype(np.float32)*.86).astype(np.uint8)
    torso[fill] = shaded[fill]
    # Close the hairline left along the mirror axis.
    for x in range(MIRROR_X-3, MIRROR_X+5):
        gap = (torso[250:300, x, 3] < 200) & (torso[250:300, MIRROR_X-4, 3] >= 200)
        torso[250:300, x][gap] = torso[250:300, MIRROR_X-4][gap]
    # Collar and the far shoulder's slope, which the sack's neck lay across.
    neck = polygon([(176, 238), (206, 238), (232, 253), (238, 264), (172, 262)]) & (torso[..., 3] < 120)
    torso[neck] = (26, 26, 30, 255)
    save('torso', torso)

    back = mirrored(cut(solid, arm_upper))
    back[..., :3] = (back[..., :3].astype(np.float32)*.78).astype(np.uint8)
    save('arm_back_upper', back)
    back = mirrored(cut(solid, arm_lower & ~polygon([(138, 250), (166, 252), (167, 288), (139, 288)])))
    back[..., :3] = (back[..., :3].astype(np.float32)*.78).astype(np.uint8)
    save('arm_back_lower', back)

    # Where the puppet's hand grips the neck of the sack: wood, not cloth.
GRIP = [(222, 226), (262, 226), (282, 262), (292, 302), (262, 312), (224, 300)]


def whole_sack(cloth, sack):
    """The sack with nothing in front of it: the bite the body took out of
    its outline is closed, and that area and the gripping hand are painted
    over with cloth grown in from what is visible around them."""
    rows, cols = np.indices((H, W))
    mask = sack & (cloth[..., 3] > 40)
    # Only the sack proper: the flap showing behind the near arm would drag
    # the outline out to the left once the body is no longer in the way.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    mask = labels == 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    value = cloth[..., :3].max(axis=2)
    # Dark pixels on its body side are the hand, the shirt and their shadow.
    good = mask & ~((value < 128) & (cols < 262) & (rows > 196))
    good = cv2.erode(good.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed)
    biggest = 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    outline = labels == biggest
    outline = cv2.GaussianBlur(outline.astype(np.float32), (0, 0), 3) > .5
    outline &= (rows >= 108) | mask
    painted = cv2.inpaint(np.ascontiguousarray(cloth[..., :3]), (~good).astype(np.uint8)*255, 9, cv2.INPAINT_TELEA)
    # Inpainting is smooth; give the new cloth a little of the weave back.
    weave = np.random.default_rng(7).normal(0, 5, (H, W, 1))
    patched = np.clip(painted.astype(np.float32)+weave*(~good)[..., None], 0, 255).astype(np.uint8)
    out = np.zeros_like(cloth)
    out[..., :3] = np.where(good[..., None], cloth[..., :3], patched)
    soft = cv2.GaussianBlur(outline.astype(np.float32), (0, 0), 1.2)
    out[..., 3] = np.where(good, np.maximum(cloth[..., 3], 200), 232*soft).astype(np.uint8)
    out[~outline & ~good] = 0
    return out


# (see main) The sack on its own, as it lies on the ground after the fall.
    ys, xs = np.where(full[..., 3] > 30)
    crop = full[ys.min():ys.max()+1, xs.min():xs.max()+1]
    cv2.imencode('.png', crop)[1].tofile(str(SKIN/'sack.png'))
    print('layers written to', SKIN/'layers')


if __name__ == '__main__':
    main()
