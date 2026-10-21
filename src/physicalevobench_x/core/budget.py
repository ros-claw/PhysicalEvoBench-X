from dataclasses import dataclass, field


@dataclass
class BudgetLedger:
    exploration_cap: int
    validation_cap: int
    charged: dict = field(default_factory=lambda: {'exploration': 0, 'validation': 0})
    infra_retries: int = 0
    logical_requests: int = 0
    attempts: list = field(default_factory=list)

    def require_room(self, phase):
        if phase not in self.charged or self.charged[phase] >= getattr(self, phase+'_cap'):
            raise ValueError('Budget exhausted or unknown phase')
        self.logical_requests += 1

    def record(self, result):
        self.attempts.append(result)
        if not result.infra_failure:
            self.charged[result.phase] += 1

    def retry(self):
        if self.infra_retries >= 2:
            raise RuntimeError('INCOMPLETE: run infrastructure retry limit reached')
        self.infra_retries += 1

    def snapshot(self):
        return dict(charged=self.charged.copy(), infra_retries=self.infra_retries,
            logical_episode_requests=self.logical_requests,
            physical_episode_executions=len(self.attempts),
            budget_charged_episodes=sum(self.charged.values()),
            sim_time_s=sum(r.sim_time_s for r in self.attempts),
            wall_time_s=sum(r.wall_time_s for r in self.attempts))
