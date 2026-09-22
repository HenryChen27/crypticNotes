import math

DURATIONS = {'heart': 3600, 'happy': 3600, 'angry': 2200,
             'puzzled': 2200, 'sleep': 2200, 'curious': 2200}


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

