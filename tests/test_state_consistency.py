"""CPU-only fixtures for quaternion derivative checks, not physics validation."""
from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from state_consistency_metrics import angular_pose_increments


def test_known_constant_spin_and_quaternion_sign_changes():
    t=np.arange(21)*.005
    q=np.array([[0.,0.,np.sin(.2*x/2),np.cos(.2*x/2)] for x in t])
    q[::2]*=-1
    expected=np.tile([0.,0.,.2],(20,1))
    np.testing.assert_allclose(angular_pose_increments(t,q),expected,atol=1e-12)


def test_still_pose_is_not_assumed_to_match_native_velocity():
    result=angular_pose_increments([0.,.02,.04],[[0.,0.,0.,1.]]*3)
    np.testing.assert_allclose(result,0.)
    with pytest.raises(ValueError,match='increasing'):
        angular_pose_increments([0.,0.],[[0.,0.,0.,1.]]*2)
