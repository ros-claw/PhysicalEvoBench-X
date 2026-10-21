"""Precomputed private conditions; never pass this object to a proposer."""
import random
from .hashing import digest

SPLITS = ('dev', 'source_train', 'source_validation', 'source_audit',
          'target_train', 'target_validation', 'target_test')


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
            randomization_version='dev_v1') for i in range(count)]
    return manifests
