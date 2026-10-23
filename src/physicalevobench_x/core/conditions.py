"""Precomputed private conditions; never pass this object to a proposer."""
import random
import math
from .hashing import digest

SPLITS = ('dev', 'source_train', 'source_validation', 'source_audit',
          'target_train', 'target_validation', 'target_test')


def validate_condition(condition):
    expected = {'condition_id','split','reset_seed','offset_xy_m','yaw_rad','mass_kg',
                'size_m','initial_velocity','settle_time_s','randomization_version'}
    if set(condition) != expected or condition['split'] not in SPLITS:
        raise ValueError('Unsupported private condition fields/split')
    if (type(condition['reset_seed']) is not int or not 0 <= condition['reset_seed'] < 2**31
        or condition['size_m'] != [.045,.045,.065] or condition['initial_velocity'] != [0.]*6
        or condition['settle_time_s'] != .5 or condition['randomization_version'] not in ('dev_v1','stable_lift_v1')):
        raise ValueError('Unsupported reset/geometry/dynamics contract')
    offset = condition['offset_xy_m']
    if not isinstance(offset,(tuple,list)) or len(offset)!=2:
        raise ValueError('Unsupported condition offset')
    numbers = [condition['mass_kg'],condition['yaw_rad'],*offset]
    if (len(offset)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in numbers)
        or not .1 <= condition['mass_kg'] <= .5 or abs(condition['yaw_rad']) > .1745329252
        or any(abs(v)>.03 for v in offset)):
        raise ValueError('Private condition outside frozen physical distribution')
    if not isinstance(condition['condition_id'],str) or not condition['condition_id']:
        raise ValueError('Missing condition ID')
    return condition


def generate(seed, counts):
    manifests = {}
    for split, count in counts.items():
        if split not in SPLITS:
            raise ValueError(split)
        rng = random.Random(int(digest({'seed': seed, 'split': split}), 16))
        manifests[split] = [dict(condition_id=digest([seed, split, i])[:24], split=split,
            reset_seed=rng.randrange(2**31), offset_xy_m=[rng.uniform(-.03, .03) for _ in range(2)],
            yaw_rad=rng.uniform(-.1745329252, .1745329252), mass_kg=rng.uniform(.1, .5),
            size_m=[.045, .045, .065], initial_velocity=[0.]*6, settle_time_s=.5,
            randomization_version='stable_lift_v1') for i in range(count)]
    return manifests
