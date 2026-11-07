"""磷焰矿灯: a frost-grown mine lamp whose cracked lens is its eye."""
from pathlib import Path
from .rig import CANVAS, PARTS, PIVOTS, LENS, CORE, GROUND_Y, SHADOW
from .animation import pose, body_motion, flight, DURATIONS, LOOPING, STAGE_MOODS, CHANNELS, HOVER, HOVER_DEFAULT
from .effects import paint_effects, paint_stage, paint_glints, paint_motes, stage_rect, laser_angle, laser_strength, fire_position

IMAGE = Path(__file__).with_name('image.png')
NAME = '磷焰矿灯'
