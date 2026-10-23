import random
from ..core.schemas import bounds_for, SkillSpec


class RandomSearch:
    learner_id = 'random_search_v1'

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.proposals = []

    def propose(self, incumbent, history):
        raw, parameters = {}, {}
        for key, (lo, hi) in bounds_for(incumbent).items():
            x = (getattr(incumbent.parameters, key)-lo)/(hi-lo)
            raw[key] = x + self.rng.gauss(0, .2)
            y = raw[key] % 2
            parameters[key] = lo + (1-abs(y-1))*(hi-lo)
        data = incumbent.model_dump()
        data['parameters'] = parameters
        result = SkillSpec.model_validate(data)
        self.proposals.append({'raw_normalized': raw, 'skill': result.model_dump()})
        return result
