"""Joints of the 守财木偶 on its 444×484 image.

The layers themselves are pre-cut PNGs in ``layers/`` (see
scripts/build_puppet_layers.py for why they are not polygons): the sack has
to come off, and what it hid had to be painted in.

The figure is drawn in three-quarter view facing left, so "forward" is
towards smaller x. A positive limb angle swings that limb forward; a negative
``lean`` tips the whole body forward over its feet.
"""
CANVAS = (444, 484)

# Back to front. The first group sits behind the legs, the second in front.
LAYERS = ('sack', 'sack_front', 'head', 'torso', 'arm_upper', 'arm_lower',
          'arm_back_upper', 'arm_back_lower',
          'leg_l_upper', 'leg_l_lower', 'leg_r_upper', 'leg_r_lower')

PIVOTS = {
    'root': (206, 432),             # between the shoes: leaning and squash
    'waist': (206, 345),            # the upper body follows through here
    'neck': (188, 250),
    'shoulder': (158, 262),
    'elbow': (152, 297),
    'back_shoulder': (254, 262),    # mirror of the near arm about x=206
    'back_elbow': (260, 297),
    'hip_l': (177, 348), 'knee_l': (176, 378),
    'hip_r': (237, 348), 'knee_r': (238, 378),
    'sack': (228, 236),             # slung over this shoulder
}

HAND = (122, 362)           # the near hand at rest
REACH = (64, 268)           # ... and stretched out in front
EYE = (132, 196)
MOUTH = (124, 226)
HAT_TIP = (190, 62)
SACK_CENTRE = (300, 250)
GROUND_Y = 434
# Feet only, and with the sack on the back.
SHADOW = dict(bare=((206, 436), (62, 9)), laden=((238, 436), (104, 11)))
