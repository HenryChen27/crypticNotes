"""Layer outlines and joints of the 磷焰矿灯 on its 444×484 image.

Each part is a list of polygons (their union is the layer's mask). Parts
partition the image along the handle wires, so a rotating handle or a
rattling crystal cluster never tears the lamp box.
"""
CANVAS = (444, 484)

PARTS = {
    # Cap, box with the cracked lens, bottom bar and the small lower crystals.
    'body': [[(188,98),(292,98),(300,214),(318,214),(334,238),(346,258),(352,290),(352,393),
              (156,393),(156,262),(164,250),(182,214)]],
    # Wire handle with its ring: left wire, bar + ring, right wire.
    'handle': [[(164,214),(175,84),(190,84),(182,214)],
               [(176,82),(227,82),(227,60),(233,51),(253,51),(259,60),(259,82),(304,82),(304,98),(176,98)],
               [(291,84),(307,84),(318,214),(300,214)]],
    # Loose chain hanging off the left bracket.
    'chain': [[(92,198),(128,198),(128,306),(92,306)]],
    # Ice growing out of the cap, either side.
    'left_crystal': [[(18,18),(176,18),(176,84),(164,214),(164,250),(128,250),(128,198),(18,198)]],
    'right_crystal': [[(307,84),(330,50),(402,50),(402,258),(346,258),(334,238),(318,214)]],
    # Two short legs under the bottom bar.
    'left_leg': [[(206,390),(240,390),(240,446),(206,446)]],
    'right_leg': [[(260,390),(292,390),(292,440),(260,440)]],
}

PIVOTS = {
    'ring': (243, 62),          # held here while carried
    'handle': (240, 214),       # the wires hinge on the cap
    'chain': (110, 200),
    'left_crystal': (168, 210),
    'right_crystal': (318, 212),
    'left_leg': (223, 392),
    'right_leg': (276, 392),
    'base': (250, 442),         # tips over its feet
}

# The cracked glass and the light behind it.
LENS = dict(center=(247, 290), radii=(58, 76))
CORE = (234, 288)
GROUND_Y = 442
SHADOW = dict(center=(250, 446), radii=(72, 10))
