import math
import numpy as np


def trapezoid_distance(t, distance, vmax, amax):
    """Analytic rest-to-rest trajectory, bounded speed AND acceleration."""
    if min(distance, vmax, amax) <= 0:
        raise ValueError('positive trajectory parameters required')
    ramp = min(vmax/amax, math.sqrt(distance/amax))
    peak = amax*ramp
    cruise = max(0., (distance-amax*ramp*ramp)/peak)
    end = 2*ramp+cruise
    t = max(0., min(t, end))
    if t <= ramp:
        x = .5*amax*t*t
    elif t <= ramp+cruise:
        x = .5*amax*ramp*ramp+peak*(t-ramp)
    else:
        x = distance-.5*amax*(end-t)**2
    return x, end


def segment(start, goal, t, vmax, amax):
    delta = np.asarray(goal)-start
    length = float(np.linalg.norm(delta))
    if length < 1e-10:
        return np.asarray(goal), True
    distance, duration = trapezoid_distance(t, length, vmax, amax)
    return np.asarray(start)+delta*(distance/length), t >= duration
