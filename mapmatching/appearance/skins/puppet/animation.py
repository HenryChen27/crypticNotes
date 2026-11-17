"""Poses of the 守财木偶.

``pose`` returns one angle per channel, all zero at rest:

- ``head``: about the neck; negative nods forward.
- ``arm`` / ``fore``: the near arm at the shoulder and the elbow.
- ``back_arm`` / ``back_fore``: the far arm, only seen once the sack is off.
- ``leg_l`` / ``knee_l`` / ``leg_r`` / ``knee_r``: hips and knees (a knee
  only bends backwards, so its angle is never positive).
- ``sack``: the sack swinging on the shoulder.
- ``lean``: the whole figure tipping over its feet; negative is forward.
- ``drop``: 0 with the sack on its back, 1 with the sack set down on the
  ground behind it (it does this to stretch, to stamp, to sleep).

Besides the moods every body has, there are the ones the cursor theft plays
(see appearance/heist.py): sneak (a stroll with its hands behind its back),
freeze, grab, run, trip, down, getup, cry,
hit, sulk, rejoice, walk.
"""
import math

DURATIONS = {'heart': 2600, 'happy': 2600, 'angry': 2800,
             'puzzled': 2200, 'sleep': 2200, 'curious': 2000,
             'tilt': 1800, 'shift': 1700, 'stretch': 3200,
             'doze': 4000, 'wake': 1800, 'land': 600,
             'sneak': 1200, 'freeze': 2400, 'grab': 800, 'run': 520,
             'trip': 700, 'down': 1600, 'getup': 1100, 'cry': 1100,
             'hit': 1500, 'sulk': 2000, 'rejoice': 1800, 'walk': 700}

LOOPING = ('matching', 'doze', 'sneak', 'freeze', 'run', 'down', 'cry', 'hit', 'sulk', 'walk')
# One-shots that keep their last frame until the next pose is asked for.
HOLD = ('grab', 'trip', 'getup')
# Hands clasped behind the back: the near arm is drawn behind the body.
ARM_BEHIND = ('sneak', 'freeze')
HEIST_MOODS = ('sneak', 'freeze', 'grab', 'run', 'trip', 'down', 'getup', 'cry', 'hit', 'sulk', 'rejoice', 'walk')

CHANNELS = ('head', 'arm', 'fore', 'back_arm', 'back_fore',
            'leg_l', 'knee_l', 'leg_r', 'knee_r', 'sack', 'lean', 'drop')

# Where the sack sits when it has been set down (``drop`` = 1): this far from
# where it hangs on the back, and tipped this much.
SACK_DOWN = dict(x=44., y=74., turn=11., arc=46.)

# How far the root slides back inside the widget when the figure lies down,
# so that its length still fits (canvas px).
LIE_SHIFT = 200.
LIE_LEAN = -78.
# Lying on its front the figure is as thick as it is deep: keep it off the floor.
LIE_RAISE = 26.


def _smooth(value):
    x = max(0., min(1., value))
    return x*x*(3-2*x)


def _bump(t, centre, width):
    return max(0., 1-abs(t-centre)/width)


def _held(t, down=.16, up=.84, ramp=.14):
    """0→1 by `down`, held, back to 0 from `up`: the sack off and on again."""
    return _smooth(t/ramp if down <= ramp else (t-(down-ramp))/ramp)*(1-_smooth((t-up)/ramp))


def _swing(u):
    """One windmill of an arm, `u` 0..1: it drops back behind the body, comes
    up and over the top, and lands in front. Returns shoulder, elbow, and how
    far through the blow the body is (-1 wound right back … +1 landed).

    The shoulder turns one whole circle backwards, so it ends a full turn
    from where it began: -314° is the resting 46° again.
    """
    if u <= 0 or u >= 1:
        return 46., 30., 0.
    if u < .5:
        k = _smooth(u/.5)                   # slowly, down and back and up behind
        return 46-196*k, 30-22*k, -k
    if u < .64:
        k = ((u-.5)/.14)**2                 # over the top and down, fast
        return -150-140*k, 8-4*k, -1+2*k
    k = _smooth((u-.64)/.36)                # and back to its side
    return -290-24*k, 4+26*k, 1-k


def _step(phase):
    """Hip and knee of one leg through a stride; `phase` in radians."""
    return math.sin(phase), -max(0., math.cos(phase-.5))


def body_motion(mood, progress):
    """Root offset, upper-body follow-through and squash."""
    t = max(0., min(1., progress))
    envelope = math.sin(math.pi*t)**2
    phase = 2*math.pi*t
    if mood == 'idle':
        breath = (1-math.cos(phase))*.5
        return dict(x=0., y=-4*breath, torso=.6*math.sin(phase), squash=-.012*breath)
    if mood == 'matching':
        return dict(x=5*math.sin(phase), y=-5*(1-math.cos(2*phase))*.5, torso=2.5*math.sin(phase), squash=0.)
    if mood == 'doze':
        breath = (1-math.cos(phase))*.5
        return dict(x=0., y=3-2*breath, torso=-1.5*breath, squash=.02-.012*breath)
    if mood == 'stretch':
        return dict(x=0., y=-8*envelope, torso=3*envelope, squash=-.03*envelope)
    if mood == 'shift':
        drift = math.sin(phase)
        return dict(x=10*drift*envelope, y=-3*abs(drift)*envelope, torso=-3*drift*envelope, squash=0.)
    if mood == 'tilt':
        return dict(x=0., y=0., torso=2*envelope, squash=0.)
    if mood == 'wake':
        rise = math.sin(math.pi*t)
        return dict(x=0., y=-12*rise, torso=0., squash=.02*rise)
    if mood == 'land':
        bounce = math.sin(math.pi*t)*(1-t)
        return dict(x=0., y=5*bounce, torso=0., squash=.09*bounce)
    if mood == 'curious':
        return dict(x=0., y=-6*envelope, torso=-2*envelope, squash=0.)
    if mood in ('heart', 'happy'):
        hop = abs(math.sin(phase*1.5))*envelope
        return dict(x=0., y=-46*hop, torso=3*math.sin(phase*1.5)*envelope, squash=.03*(.5-hop)*envelope)
    if mood == 'angry':
        beat = math.sin(phase*6)
        return dict(x=4*math.sin(phase*12)*envelope, y=-6*abs(beat)*envelope,
                    torso=4*beat*envelope, squash=.02*beat*envelope)
    if mood == 'sneak':
        return dict(x=0., y=-4*abs(math.sin(phase)), torso=1.5*math.sin(phase), squash=0.)
    if mood == 'freeze':
        rock = math.sin(phase*2)
        return dict(x=0., y=-5*max(0., rock), torso=1.5*rock, squash=0.)
    if mood == 'grab':
        return dict(x=-14*_bump(t, .42, .3), y=0., torso=-6*_bump(t, .42, .3), squash=0.)
    if mood == 'run':
        return dict(x=0., y=-16*abs(math.sin(phase)), torso=-4+3*math.sin(phase*2), squash=0.)
    if mood == 'trip':
        fall = _smooth(t/.7)**2
        thud = _bump(t, .82, .16)
        return dict(x=LIE_SHIFT*fall, y=-22*math.sin(math.pi*min(1., t/.6))-LIE_RAISE*fall+6*thud, torso=0., squash=.05*thud)
    if mood == 'down':
        return dict(x=LIE_SHIFT, y=-LIE_RAISE, torso=1.5*math.sin(phase), squash=0.)
    if mood == 'getup':
        rise = _smooth((t-.15)/.7)
        return dict(x=LIE_SHIFT*(1-rise), y=-LIE_RAISE*(1-rise)-10*math.sin(math.pi*rise), torso=0., squash=0.)
    if mood == 'cry':
        return dict(x=0., y=5-3*abs(math.sin(phase)), torso=-4+2*math.sin(phase*2), squash=.02)
    if mood == 'hit':
        blow = _swing(t*2)[2]+_swing(t*2-1)[2]
        return dict(x=-7*max(0., blow)+3*max(0., -blow), y=-7*max(0., -blow), torso=-3-6*blow, squash=.02*max(0., blow))
    if mood == 'sulk':
        sob = max(0., math.sin(phase*2))
        return dict(x=0., y=20-3*sob, torso=-6-2*sob, squash=.1)
    if mood == 'rejoice':
        hop = abs(math.sin(phase*2))*envelope
        return dict(x=0., y=-58*hop, torso=4*math.sin(phase*2)*envelope, squash=.03*(.5-hop)*envelope)
    if mood == 'walk':
        return dict(x=0., y=-6*abs(math.sin(phase)), torso=-1+1.5*math.sin(phase*2), squash=0.)
    return dict(x=0., y=0., torso=0., squash=0.)


def pose(mood, progress):
    t = max(0., min(1., progress))
    ramp = min(1., t/.22, (1-t)/.25)
    ease = ramp*ramp*(3-2*ramp)
    phase = 2*math.pi*t
    a = {k: 0. for k in CHANNELS}
    if mood == 'idle':
        sway = math.sin(phase)
        a.update(head=1.5*sway, arm=2*sway, back_arm=-2*sway, sack=1.2*sway)
        return a, 0.
    if mood == 'matching':
        # Looks about for something worth having, one foot tapping.
        sweep = math.sin(phase)
        tap = max(0., math.sin(phase*4))
        a.update(head=10*sweep, arm=10*sweep, fore=14, back_arm=-10*sweep, sack=-5*sweep,
                 leg_l=8*tap, knee_l=-10*tap)
        return a, 0.
    if mood == 'doze':
        breath = (1-math.cos(phase))*.5
        # Sack off, propped against it, chin on its chest.
        a.update(drop=1., head=-19-2*breath, lean=7., arm=3., fore=8., back_arm=-14., back_fore=-10.,
                 leg_l=10., knee_l=-12., leg_r=6., knee_r=-8.)
        return a, 0.
    if mood == 'wake':
        shake = math.sin(t*math.pi*6)*ease
        # Starts awake with the sack still on the ground, and swings it up.
        down = _smooth(t/.06)*(1-_smooth((t-.3)/.3))
        a.update(drop=down, head=8*shake, arm=70*ease, fore=20*ease, back_arm=(70+50*down)*ease, sack=-6*shake)
        return a, ease
    if mood == 'tilt':
        a.update(head=12*ease, arm=-4*ease, sack=3*ease)
        return a, ease
    if mood == 'shift':
        drift = math.sin(phase)*ease
        a.update(head=-3*drift, leg_l=10*drift, knee_l=-8*max(0., drift), leg_r=6*drift, sack=-6*drift, arm=5*drift)
        return a, ease
    if mood == 'stretch':
        # Sets the sack down first: both arms are free to go right up.
        down = _held(t)
        reach = _smooth((t-.2)/.2)*(1-_smooth((t-.62)/.2))
        a.update(drop=down, head=10*reach, arm=166*reach, fore=12*reach, back_arm=158*reach, back_fore=8*reach,
                 lean=5*reach, leg_l=-3*reach, leg_r=3*reach)
        return a, reach
    if mood == 'land':
        settle = math.sin(t*math.pi)*(1-t)
        a.update(arm=-16*settle, back_arm=-16*settle, sack=10*settle, knee_l=-14*settle, knee_r=-14*settle, head=-5*settle)
        return a, 0.
    if mood == 'curious':
        flutter = math.sin(t*math.pi*10)*ease
        a.update(head=6*ease, arm=118*ease, fore=28*ease+16*flutter, sack=-3*ease)
        return a, ease
    if mood in ('heart', 'happy'):
        swing = math.sin(phase*1.5)
        a.update(head=7*swing*ease, arm=(128+14*swing)*ease, fore=18*ease, back_arm=(128-14*swing)*ease,
                 sack=9*swing*ease, leg_l=-10*max(0., swing)*ease, knee_l=-22*max(0., swing)*ease,
                 leg_r=8*max(0., -swing)*ease, knee_r=-22*max(0., -swing)*ease)
        return a, ease
    if mood == 'angry':
        # Throws the sack down and shakes both fists.
        beat = math.sin(t*math.pi*12)
        a.update(drop=_held(t, down=.12, up=.86, ramp=.1),
                 head=(-4+7*math.sin(t*math.pi*12-.6))*ease, arm=(84+30*beat)*ease, fore=(46+30*beat)*ease,
                 back_arm=(84-30*beat)*ease, back_fore=(46-30*beat)*ease, lean=-5*ease,
                 leg_l=16*max(0., beat)*ease, knee_l=-26*max(0., beat)*ease,
                 leg_r=16*max(0., -beat)*ease, knee_r=-26*max(0., -beat)*ease)
        return a, ease
    if mood == 'puzzled':
        flutter = math.sin(t*math.pi*12)*ease
        a.update(head=13*ease, arm=62*ease, fore=96*ease+6*flutter, sack=4*ease, lean=2*ease)
        return a, ease
    if mood == 'sleep':
        a.update(drop=_held(t), head=-15*ease, lean=5*ease, arm=8*ease, fore=18*ease, back_arm=-12*ease)
        return a, ease
    # ── the cursor theft ─────────────────────────────────────────
    if mood == 'sneak':
        # Just out for a stroll: hands behind its back, nose in the air,
        # whistling, and not looking at the pointer at all.
        hl, kl = _step(phase)
        hr, kr = _step(phase+math.pi)
        a.update(lean=6., head=25+2.5*math.sin(phase*2), arm=-34+3*math.sin(phase), fore=-58.,
                 back_arm=-18., back_fore=-30.,
                 leg_l=15*hl, knee_l=20*kl, leg_r=15*hr, knee_r=20*kr, sack=3*math.sin(phase*2))
        return a, 0.
    if mood == 'freeze':
        # The mouse moved: it stops dead in the same pose and rocks on its
        # heels, finding the sky very interesting.
        rock = math.sin(phase*2)
        a.update(lean=6., head=28+2*rock, arm=-34., fore=-58., back_arm=-18., back_fore=-30., sack=2*rock,
                 leg_l=-2*rock, leg_r=2*rock)
        return a, 0.
    if mood == 'grab':
        reach = _bump(t, .42, .32)
        hold = _smooth((t-.5)/.4)
        a.update(lean=-12*reach, head=-6*reach, arm=92*reach+34*hold, fore=10*reach+62*hold,
                 sack=-5*reach, leg_l=10*reach, knee_r=-12*reach)
        return a, 0.
    if mood == 'run':
        hl, kl = _step(phase)
        hr, kr = _step(phase+math.pi)
        a.update(lean=-16., head=-3+3*math.sin(phase*2), arm=34-34*hl, fore=62.,
                 back_arm=34-34*hr, back_fore=62.,
                 leg_l=44*hl, knee_l=64*kl, leg_r=44*hr, knee_r=64*kr, sack=9*math.sin(phase*2))
        return a, 0.
    if mood == 'trip':
        fall = _smooth(t/.7)**2
        a.update(lean=-16+(LIE_LEAN+16)*fall, head=12*fall, arm=34+96*fall, fore=62*(1-fall)+8*fall,
                 back_arm=34+84*fall, back_fore=62*(1-fall),
                 leg_l=-26*fall, knee_l=-30*fall*(1-_bump(t, .85, .15)), leg_r=-40*fall, knee_r=-46*fall)
        return a, 0.
    if mood == 'down':
        kick = math.sin(phase)
        a.update(lean=LIE_LEAN, head=12+4*math.sin(phase*2), arm=130+5*kick, fore=8., back_arm=118-5*kick,
                 leg_l=-26+5*kick, knee_l=-18*max(0., kick), leg_r=-40-5*kick, knee_r=-46+16*max(0., -kick))
        return a, 0.
    if mood == 'getup':
        rise = _smooth((t-.15)/.7)
        push = math.sin(math.pi*rise)
        a.update(lean=LIE_LEAN*(1-rise), head=12*(1-rise)-10*push, arm=130*(1-rise)+30*push, fore=40*push,
                 back_arm=118*(1-rise)+30*push, back_fore=40*push,
                 leg_l=-26*(1-rise)+18*push, knee_l=-40*push, leg_r=-40*(1-rise), knee_r=-46*(1-rise)-20*push)
        return a, 0.
    if mood == 'cry':
        # Trudging, head hung, one fist rubbing the eye.
        hl, kl = _step(phase)
        hr, kr = _step(phase+math.pi)
        rub = math.sin(phase*2)
        a.update(lean=-7., head=-19+2*rub, arm=84+5*rub, fore=118+7*rub, back_arm=6-8*hl,
                 leg_l=12*hl, knee_l=16*kl, leg_r=12*hr, knee_r=16*kr)
        return a, 0.
    if mood == 'hit':
        # A big windmilling swing with one arm, then the same with the other:
        # all wind-up and very little blow, like a child having a tantrum.
        arm, fore, blow_near = _swing(t*2)
        back_arm, back_fore, blow_far = _swing(t*2-1)
        blow = blow_near+blow_far
        a.update(lean=-5-4*blow, head=-10-7*blow, arm=arm, fore=fore, back_arm=back_arm, back_fore=back_fore,
                 leg_l=5*max(0., blow_near), knee_r=-8*max(0., -blow), leg_r=5*max(0., blow_far))
        return a, 0.
    if mood == 'sulk':
        sob = max(0., math.sin(phase*2))
        a.update(lean=-5., head=-26-3*sob, arm=8., fore=14., back_arm=8., back_fore=14.,
                 leg_l=38., knee_l=-80., leg_r=30., knee_r=-70.)
        return a, 0.
    if mood == 'rejoice':
        swing = math.sin(phase*2)
        a.update(head=8*swing*ease, arm=(146+12*swing)*ease, fore=10*ease, back_arm=(146-12*swing)*ease,
                 sack=10*swing*ease, leg_l=-12*max(0., swing)*ease, knee_l=-30*max(0., swing)*ease,
                 leg_r=10*max(0., -swing)*ease, knee_r=-30*max(0., -swing)*ease)
        return a, ease
    if mood == 'walk':
        hl, kl = _step(phase)
        hr, kr = _step(phase+math.pi)
        a.update(lean=-3., head=2*math.sin(phase*2), arm=-20*hl, fore=12., back_arm=-20*hr, back_fore=12.,
                 leg_l=24*hl, knee_l=30*kl, leg_r=24*hr, knee_r=30*kr, sack=4*math.sin(phase*2))
        return a, 0.
    return a, ease
