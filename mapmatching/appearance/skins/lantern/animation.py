"""Poses of the 磷焰矿灯.

The lamp hovers: at rest it floats a little above the ground on its own
light, and it settles onto its legs only to doze. ``pose`` returns joint
angles plus the light's own channels, every one of them zero at rest so
looping moods can be blended in:

- ``tilt``: whole lamp tipping over its feet (degrees).
- ``handle``, ``chain``, ``left_crystal``, ``right_crystal``, ``left_leg``,
  ``right_leg``: part rotations about their pivots.
- ``glow``: brightness change of the light (-1 dark … +1 flare).
- ``blink``: the light going out for a moment (0 lit … 1 out).
- ``squint``: the lens narrowing to a slit (0 … 1).
- ``scan``: sideways drift of the bright core (-1 … 1).

``body_motion`` returns the root offset; ``HOVER`` gives the resting height
above the ground per mood, which the player eases between moods.
"""
import math

DURATIONS = {'heart': 5000, 'happy': 5000, 'angry': 3000,
             'puzzled': 2200, 'sleep': 2200, 'curious': 2000,
             'tilt': 1800, 'shift': 1700, 'stretch': 2400,
             'doze': 4000, 'wake': 1600, 'land': 600}

LOOPING = ('matching', 'doze')

# Moods whose effects reach outside the button: the laser and the ghost fire.
STAGE_MOODS = ('angry', 'heart', 'happy')

CHANNELS = ('tilt', 'handle', 'chain', 'left_crystal', 'right_crystal',
            'left_leg', 'right_leg', 'glow', 'blink', 'squint', 'scan')

# Resting height above the ground (canvas px). Dozing and hiding settle it
# onto its legs; the player eases between these.
HOVER_DEFAULT = 36.
HOVER = {'doze': 0., 'sleep': 4., 'land': 0.}


def _smooth(value):
    x = max(0., min(1., value))
    return x*x*(3-2*x)


def _bump(t, centre, width):
    """A short 0→1→0 pulse around `centre`."""
    return max(0., 1-abs(t-centre)/width)


def flight(t):
    """How far the lamp has climbed while firing the laser (0..1): lifts off
    during the charge, holds while the beam sweeps, drops at the end."""
    return _smooth(t/.16)*(1-_smooth((t-.84)/.14))


def body_motion(mood, progress):
    """Root offset, tipping and squash in the 444×484 canvas."""
    t = max(0., min(1., progress))
    envelope = math.sin(math.pi*t)**2
    phase = 2*math.pi*t
    if mood == 'idle':
        bob = (1-math.cos(phase))*.5
        return dict(x=0., y=-10*bob, torso=0., squash=0.)
    if mood == 'matching':
        # Sweeps side to side in the air like a searchlight on patrol.
        return dict(x=16*math.sin(phase), y=-12*(1-math.cos(2*phase))*.5, torso=0., squash=0.)
    if mood == 'doze':
        breath = (1-math.cos(phase))*.5
        return dict(x=0., y=-2*breath, torso=0., squash=-.008*breath)
    if mood == 'stretch':
        # Climbs high, hangs there, drops back.
        rise = math.sin(math.pi*t)**2
        return dict(x=0., y=-58*rise, torso=0., squash=.03*rise)
    if mood == 'shift':
        # Glides to one side and back, banking into the turn.
        drift = math.sin(phase)
        return dict(x=34*drift*envelope, y=-8*abs(drift)*envelope, torso=0., squash=0.)
    if mood == 'tilt':
        # Banks over and slides a little that way.
        ramp = min(1., t/.22, (1-t)/.25); ease = ramp*ramp*(3-2*ramp)
        return dict(x=-22*ease, y=-6*ease, torso=0., squash=0.)
    if mood == 'wake':
        rise = math.sin(math.pi*t)
        return dict(x=0., y=-40*rise, torso=0., squash=.02*rise)
    if mood == 'land':
        bounce = math.sin(math.pi*t)*(1-t)
        return dict(x=0., y=4*bounce, torso=0., squash=.08*bounce)
    if mood == 'curious':
        hop = math.sin(math.pi*min(1., t/.5))*(1 if t < .5 else 0)
        return dict(x=0., y=-34*hop, torso=0., squash=.015*hop)
    if mood in ('heart', 'happy'):
        # Climbs first (so the fire it spits is up out of the panel's way),
        # bobs there while the fire burns beside it, settles at the end.
        lift = _smooth(t/.16)*(1-_smooth((t-.9)/.1))
        swoop = _smooth(1-(t-.2)/.55)*_smooth((t-.14)/.08)
        bounce = abs(math.sin(phase*2))*swoop
        drift = 10*math.sin(phase*2)*swoop
        return dict(x=drift*1.6, y=-170*lift-16*bounce, torso=0., squash=.02*bounce)
    if mood == 'angry':
        lift = flight(t)
        beat = math.sin(phase*6)
        return dict(x=3*math.sin(phase*13)*envelope, y=-120*lift-3*abs(beat)*envelope,
                    torso=0., squash=.012*beat*envelope)
    return dict(x=0., y=0., torso=0., squash=0.)


def pose(mood, progress):
    t = max(0., min(1., progress))
    ramp = min(1., t/.22, (1-t)/.25)
    ease = ramp*ramp*(3-2*ramp)
    phase = 2*math.pi*t
    a = {k: 0. for k in CHANNELS}
    if mood == 'idle':
        breath = (1-math.cos(phase))*.5
        sway = math.sin(phase)
        a.update(glow=.22*breath-.11, chain=3.*sway, handle=1.5*sway, left_leg=-2*sway, right_leg=-2*sway,
                 left_crystal=.4*sway, right_crystal=-.4*sway, tilt=.8*sway)
        return a, 0.
    if mood == 'matching':
        # The core sweeps the lens like a searchlight; everything else keeps time.
        sweep = math.sin(phase)
        a.update(scan=.95*sweep, glow=.3, handle=9*sweep, chain=12*sweep, tilt=6*sweep,
                 left_leg=-8*sweep, right_leg=-8*sweep, left_crystal=3*sweep, right_crystal=3*sweep)
        return a, 0.
    if mood == 'doze':
        breath = (1-math.cos(phase))*.5
        a.update(glow=-.62+.08*breath, blink=.45, tilt=6., handle=-9., chain=3., left_crystal=1.5, right_crystal=-1.5)
        return a, 0.
    if mood == 'wake':
        shake = math.sin(t*math.pi*6)*ease
        a.update(glow=.6*ease, tilt=4*shake, chain=-8*shake, handle=6*shake,
                 left_crystal=5*shake, right_crystal=-5*shake, left_leg=-6*ease, right_leg=6*ease)
        return a, ease
    if mood == 'tilt':
        a.update(tilt=-18*ease, chain=14*ease, handle=-7*ease, scan=-.4*ease, left_leg=8*ease, right_leg=8*ease,
                 left_crystal=-3*ease, right_crystal=-3*ease)
        return a, ease
    if mood == 'shift':
        drift = math.sin(phase)*ease
        a.update(tilt=-10*drift, left_leg=-12*drift, right_leg=-10*drift, chain=14*drift, handle=5*drift,
                 scan=.35*drift)
        return a, ease
    if mood == 'stretch':
        a.update(glow=.5*ease, left_crystal=-12*ease, right_crystal=12*ease, left_leg=-10*ease, right_leg=10*ease,
                 chain=-6*ease, handle=-3*ease)
        return a, ease
    if mood == 'land':
        settle = math.sin(t*math.pi)*(1-t)
        a.update(chain=12*settle, handle=10*settle, left_crystal=4*settle, right_crystal=-4*settle,
                 left_leg=-4*settle, right_leg=4*settle)
        return a, 0.
    if mood == 'curious':
        # A glance, a double blink and a hop: hello.
        a.update(scan=.6*ease, glow=.2*ease, blink=_bump(t,.2,.07)+_bump(t,.38,.07),
                 handle=5*ease, chain=-5*math.sin(phase)*ease, tilt=-4*ease,
                 left_crystal=2*ease, right_crystal=2*ease, left_leg=-3*ease, right_leg=-3*ease)
        return a, ease
    if mood in ('heart', 'happy'):
        shimmer = math.sin(phase*4)
        swoop = _smooth(1-(t-.12)/.55)*_smooth((t-.02)/.08)
        a.update(glow=.35*ease+.18*shimmer*ease, left_crystal=5*shimmer*ease, right_crystal=-5*shimmer*ease,
                 handle=4*math.sin(phase*2)*ease, chain=-9*math.sin(phase*2)*ease, tilt=-7*math.sin(phase*2)*swoop,
                 left_leg=-6*max(0.,math.sin(phase*2))*ease, right_leg=6*max(0.,-math.sin(phase*2))*ease)
        return a, ease
    if mood == 'angry':
        lift = flight(t)
        beat = math.sin(t*math.pi*12)
        # Airborne: legs tuck in, chain streams back, the lamp leans into the beam.
        a.update(squint=ease, glow=.6*ease, tilt=3*beat*ease-5*lift,
                 left_leg=(-6+12*beat)*ease-10*lift, right_leg=(6-12*beat)*ease+10*lift,
                 left_crystal=8*math.sin(t*math.pi*14)*ease, right_crystal=-8*math.sin(t*math.pi*14+.5)*ease,
                 chain=10*math.sin(t*math.pi*13)*ease+14*lift, handle=4*beat*ease)
        return a, ease
    if mood == 'puzzled':
        # The light stutters while the lamp leans over, thinking.
        stutter = max(0., math.sin(t*27)*math.sin(t*13+1.))
        a.update(tilt=-9*ease, handle=6*ease, chain=7*ease, glow=-.5*stutter*ease, blink=.7*(stutter > .55)*ease, scan=-.3*ease)
        return a, ease
    if mood == 'sleep':
        a.update(tilt=5*ease, glow=-.6*ease, blink=.6*ease, handle=-6*ease, chain=2*ease)
        return a, ease
    return a, ease
