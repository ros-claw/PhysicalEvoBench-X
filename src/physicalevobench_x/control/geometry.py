"""SE(3), xyzw throughout; no Isaac imports on the CPU path."""
import numpy as np
from ..core.schemas import Pose


def multiply(a, b):
    av, bv = np.asarray(a[:3]), np.asarray(b[:3])
    return np.r_[a[3]*bv + b[3]*av + np.cross(av, bv), a[3]*b[3]-av@bv]


def inverse(q):
    return np.r_[-np.asarray(q[:3]), q[3]]


def rotate(q, vector):
    return multiply(multiply(q, np.r_[vector, 0.]), inverse(q))[:3]


def compose(a, b):
    return Pose(position_m=tuple(np.asarray(a.position_m)+rotate(a.quaternion_xyzw, b.position_m)),
                quaternion_xyzw=tuple(multiply(a.quaternion_xyzw, b.quaternion_xyzw)))


def invert(p):
    q = inverse(p.quaternion_xyzw)
    return Pose(position_m=tuple(-rotate(q, p.position_m)), quaternion_xyzw=tuple(q))


def relative(a, b):
    return compose(invert(a), b)


def rotvec(q):
    q = np.asarray(q, dtype=float)
    if q[3] < 0:
        q = -q
    n = np.linalg.norm(q[:3])
    return np.zeros(3) if n < 1e-12 else q[:3]*(2*np.arctan2(n, q[3])/n)


def angle(a, b):
    return float(np.linalg.norm(rotvec(multiply(a, inverse(b)))))
