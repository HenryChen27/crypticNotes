import math

DURATIONS = {'heart': 3600, 'happy': 3600, 'angry': 2200,
             'puzzled': 2200, 'sleep': 2200, 'curious': 2200,
             # Small unprompted idle actions, picked by appearance.behavior.
             'tilt': 1800, 'shift': 1700, 'stretch': 2400,
             # Looping rest state while the player is away; `wake` leaves it.
             'doze': 4000, 'wake': 1600,
             # Settling after being carried and dropped.
             'land': 600}

# Moods that loop until something else is requested, instead of returning to idle.
LOOPING = ('matching', 'doze')


def leg_weights(progress):
    """Both legs bend and settle together."""
    def smooth(value):
        x=max(0.,min(1.,value))
        return x*x*x*(10+x*(-15+6*x))
    def envelope(delay):
        return smooth((progress-.06-delay)/.28)*(1-smooth((progress-.62-delay)/.24))
    return envelope(0),envelope(0)


def body_motion(mood, progress):
    """Root bounce and torso follow-through in the 306 x 332 canvas."""
    t=max(0.,min(1.,progress))
    envelope=math.sin(math.pi*t)**2
    phase=2*math.pi*t
    if mood == 'idle':
        breath = (1-math.cos(phase))*.5
        return dict(x=0., y=-14*breath, torso=0., squash=-.025*breath)
    if mood == 'matching':
        return dict(x=3*math.sin(phase), y=-10*(1-math.cos(phase)),
                    torso=3*math.sin(phase), squash=0.)
    if mood == 'doze':
        # Half the idle breath, twice as slow: asleep, not switched off.
        breath = (1-math.cos(phase))*.5
        return dict(x=0., y=-6*breath, torso=1.5*breath, squash=-.012*breath)
    if mood == 'stretch':
        rise = math.sin(math.pi*t)**2
        return dict(x=0., y=-16*rise, torso=0., squash=.03*rise)
    if mood == 'shift':
        # Weight moves onto one leg and back; the hips drift with it.
        drift = math.sin(phase)
        return dict(x=6*drift*envelope, y=-3*abs(drift)*envelope, torso=-4*drift*envelope, squash=0.)
    if mood == 'tilt':
        return dict(x=0., y=0., torso=2.5*envelope, squash=0.)
    if mood == 'wake':
        rise = math.sin(math.pi*t)
        return dict(x=0., y=-10*rise, torso=0., squash=.02*rise)
    if mood == 'land':
        # One damped bounce after being set down.
        bounce = math.sin(math.pi*t)*(1-t)
        return dict(x=0., y=4*bounce, torso=0., squash=.07*bounce)
    if mood in ('heart','happy'):
        sway=math.sin(phase)
        return dict(x=5*sway*envelope,y=-42*envelope,
                    torso=5*sway*envelope, squash=.008*sway*envelope)
    if mood=='angry':
        beat=math.sin(phase*6)
        return dict(x=3*math.sin(phase*12)*envelope,y=-5*abs(beat)*envelope,
                    torso=5*beat*envelope,squash=.018*beat*envelope)
    return dict(x=0.,y=0.,torso=0.,squash=0.)

def pose(mood, progress):
    """Joint angles with ease-in/hold/ease-out, always returning to rest."""
    t = max(0., min(1., progress))
    ramp = min(1., t/.22, (1-t)/.25)
    ease = ramp*ramp*(3-2*ramp)
    flutter = math.sin(t*math.pi*12)*ease
    angles = dict(head=0., left_upper=0., left_lower=0.,
                  right_upper=0., right_lower=0., left_leg=0., right_leg=0.)
    if mood == 'matching':
        sway = math.sin(2*math.pi*t)
        angles.update(head=18*sway, left_upper=18*sway,
                      right_upper=18*sway, left_leg=-5*sway, right_leg=5*sway)
        return angles, 0.
    if mood == 'idle':
        sway = math.sin(2*math.pi*t)**3
        angles.update(left_upper=2.2*sway, right_upper=-1.8*sway,
                      left_lower=.7*sway, right_lower=-.6*sway,
                      left_leg=-1.4*sway, right_leg=1.7*sway)
        return angles, 0.
    if mood == 'doze':
        # Head sunk forward, arms hanging a little in: a loop with no rest frame.
        breath = (1-math.cos(2*math.pi*t))*.5
        angles.update(head=9+1.5*breath, left_upper=-4-breath, right_upper=4+breath,
                      left_lower=-3, right_lower=3)
        return angles, 0.
    if mood == 'tilt':
        angles.update(head=-13*ease, left_upper=-3*ease, right_upper=2*ease, right_leg=2*ease)
        return angles, ease
    if mood == 'shift':
        drift = math.sin(t*math.pi*2)*ease
        angles.update(head=-3*drift, left_upper=4*drift, right_upper=4*drift,
                      left_leg=-9*drift, right_leg=-7*drift)
        return angles, ease
    if mood == 'stretch':
        # Both arms up and the head back, held, then released.
        angles.update(head=-7*ease, left_upper=128*ease, left_lower=26*ease,
                      right_upper=-128*ease, right_lower=-26*ease,
                      left_leg=-2*ease, right_leg=2*ease)
        return angles, ease
    if mood == 'wake':
        shake = math.sin(t*math.pi*6)*ease
        angles.update(head=5*shake, left_upper=60*ease, right_upper=-60*ease,
                      left_lower=10*ease, right_lower=-10*ease)
        return angles, ease
    if mood == 'land':
        settle = math.sin(t*math.pi)*(1-t)
        angles.update(left_upper=-14*settle, right_upper=14*settle,
                      left_leg=-5*settle, right_leg=5*settle)
        return angles, 0.
    if mood in ('heart','happy'):
        swing=math.sin(t*math.pi*2)
        # One soft inward curl, held briefly, then released. Legs trail lift.
        angles.update(head=16*ease,
                      left_upper=-24*ease,left_lower=-42*ease,
                      right_upper=24*ease,right_lower=42*ease,
                      left_leg=(-4+7*swing)*ease,
                      right_leg=(4+5*swing)*ease)
    elif mood == 'angry':
        beat=math.sin(t*math.pi*12)
        angles.update(head=(-5+7*math.sin(t*math.pi*12-.6))*ease,
                      left_upper=(68+30*beat)*ease,left_lower=(30+38*math.sin(t*math.pi*12+.8))*ease,
                      right_upper=(-68+30*beat)*ease,right_lower=(-30+38*math.sin(t*math.pi*12+.8))*ease,
                      left_leg=(-7+13*beat)*ease,right_leg=(7-13*beat)*ease)
    elif mood == 'puzzled':
        angles.update(head=-10*ease, right_upper=-137*ease,
                      right_lower=-30*ease+7*flutter, left_upper=8*ease)
    elif mood == 'sleep':
        angles.update(head=12*ease, left_upper=-8*ease, right_upper=8*ease)
    else:
        angles.update(head=7*ease, left_upper=110*ease,
                      left_lower=35*ease+12*flutter, right_leg=-5*ease)
    return angles, ease

