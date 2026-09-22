import math

DURATIONS = {'heart': 3600, 'happy': 3600, 'angry': 2200,
             'puzzled': 2200, 'sleep': 2200, 'curious': 2200}


def body_motion(mood, progress):
    """Root bounce and torso follow-through in the 306 x 332 canvas."""
    t=max(0.,min(1.,progress))
    envelope=math.sin(math.pi*t)**2
    phase=2*math.pi*t
    if mood in ('heart','happy'):
        sway=math.sin(phase*2)
        hop=math.sin(phase*3)
        return dict(x=7*sway*envelope,y=-22*abs(hop)*envelope,
                    torso=7*sway*envelope, squash=.025*hop*envelope)
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
        swing=math.sin(t*math.pi*4)
        # Head trails the torso; bent forearms stay close to the cheeks.
        angles.update(head=(-8-11*math.sin(t*math.pi*4-.5))*ease,
                      left_upper=(36+18*swing)*ease,left_lower=(95+15*flutter)*ease,
                      right_upper=(-36+18*swing)*ease,right_lower=(-95+15*flutter)*ease,
                      left_leg=(-10+18*math.sin(t*math.pi*6))*ease,
                      right_leg=(10+18*math.sin(t*math.pi*6+1))*ease)
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

