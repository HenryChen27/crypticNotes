"""守财木偶: a wooden thief with a sack it will not put down.

Artwork from the 第五人格 BWIKI 加页手记 pages (https://wiki.biligame.com/dwrg/加页手记),
non-commercial use; the 辞章 icons in ``relics/`` come from the same wiki.
"""
from pathlib import Path
from .rig import (CANVAS, LAYERS, PIVOTS, HAND, REACH, EYE, MOUTH, HAT_TIP, SACK_CENTRE,
                  GROUND_Y, SHADOW)
from .animation import (pose, body_motion, DURATIONS, LOOPING, HOLD, HEIST_MOODS, ARM_BEHIND, CHANNELS,
                        LIE_SHIFT, LIE_LEAN, SACK_DOWN)
from .effects import paint_extras, paint_stars

IMAGE = Path(__file__).with_name('image.png')
LAYER_DIR = Path(__file__).with_name('layers')
SACK_IMAGE = Path(__file__).with_name('sack.png')
RELIC_DIR = Path(__file__).with_name('relics')
NAME = '守财木偶'
