"""Pose-increment checks, independent of native velocity buffers."""
import numpy as np


def angular_pose_increments(times, xyzw):
    times=np.asarray(times,dtype=float)
    q=np.asarray(xyzw,dtype=float)
    if q.shape!=(len(times),4) or len(times)<2 or np.any(np.diff(times)<=0):
        raise ValueError('At least two strictly increasing pose samples required')
    norms=np.linalg.norm(q,axis=1)
    if np.any(norms<1e-12) or not np.isfinite(q).all():raise ValueError('Invalid quaternion')
    q=q/norms[:,None]
    # q_next * conjugate(q_previous), shortest representation, in world axes.
    previous,current=q[:-1],q[1:]
    vector=(current[:,:3]*previous[:,3:]-previous[:,:3]*current[:,3:]
            -np.cross(current[:,:3],previous[:,:3]))
    scalar=np.sum(current*previous,axis=1)
    sign=np.where(scalar<0,-1.,1.)
    vector=vector*sign[:,None]
    magnitude=np.linalg.norm(vector,axis=1)
    angle=2*np.arctan2(magnitude,np.abs(scalar))
    scale=np.divide(angle,magnitude,out=np.full_like(angle,2.),where=magnitude>1e-12)
    return vector*scale[:,None]/np.diff(times)[:,None]
