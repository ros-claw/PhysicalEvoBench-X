"""Post-hoc description of frozen pilot records, not new generalization evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
from diagnostic_metrics import measure_episode
from physicalevobench_x.core.hashing import write_json
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.protocol.learning import reconstruct


def analyze(suite):
    groups, adaptation = [], []
    for learner in ('random_search_v1', 'bounded_llm_v1'):
        package = suite/'packages'/learner/'franka_robotiq/seed-0'
        source_path = Path(json.loads((package/'stages/source/complete.json').read_text())['output'])
        before = SkillSpec.model_validate_json((source_path/'before.json').read_text())
        after = SkillSpec.model_validate(reconstruct(source_path)['skill'])
        for stage in ('source_audit', 'evaluation_0'):
            selected_path=Path(json.loads((package/'stages'/stage/'complete.json').read_text())['output'])
            attempts=[json.loads(l) for l in (selected_path/'pair_attempts.jsonl').read_text().splitlines()]
            excluded={eid for row in attempts if not row['included'] for eid in row['episode_ids']}
            entries = [json.loads(p.read_text()) for p in
                       sorted((package/'stages'/stage/'journal/physical').glob('[0-9]*.json'))]
            for label, skill in (('before', before), ('after', after)):
                records = [e['result'] for e in entries if e['status']=='COMPLETE'
                           and not e['result']['infra_failure'] and e['result']['skill_hash']==skill.semantic_hash
                           and e['result']['episode_id'] not in excluded]
                if len(records)!=50 or len({r['condition_id'] for r in records})!=50:
                    raise ValueError('Incomplete or duplicate historical paired conditions')
                measured = [measure_episode(r) for r in records]
                failures = [m for m in measured if not m['task_success']]
                groups.append(dict(learner=learner, source='franka_robotiq', stage=stage, side=label,
                    skill=skill.model_dump(), episodes=len(records), successes=sum(r['task_success'] for r in records),
                    failure_reasons=dict(Counter(m['termination_reason'] for m in failures)),
                    failures_reached_lift=sum(m['max_lift_m']>=.08 for m in failures),
                    failures_no_hold=sum(m['hold_time_s']==0 for m in failures),
                    failures_angular_blocked_every_elevated_sample=sum(
                        m['measurements']['elevated_angular_over_limit_fraction']==1. for m in failures),
                    failure_elevated_angular_medians_radps=[m['measurements']['elevated_angular_median_radps'] for m in failures],
                    successful_completion_median_s=median(r['completion_time_s'] for r in records if r['task_success'])
                        if any(r['task_success'] for r in records) else None,
                    # Detailed evidence stays local; no private conditions are exported.
                    measurements=measured))
        for budget in (0,5,20):
            for side in ('before','after'):
                stage=f'target_{budget}_{side}'
                path=Path(json.loads((package/'stages'/stage/'complete.json').read_text())['output'])
                rebuilt=reconstruct(path)
                selection=json.loads((path/'selection.json').read_text())
                records={r['episode_id']:r for r in
                    map(json.loads,(path/'episode_results.jsonl').read_text().splitlines())} if budget else {}
                validation={}
                for which in ('before','candidate'):
                    rows=[records[eid] for eid in selection.get('validation_'+which,[])]
                    success=[r['completion_time_s'] for r in rows if r['task_success']]
                    validation[which]=dict(episodes=len(rows),successes=sum(r['task_success'] for r in rows),
                        successful_completion_median_s=median(success) if success else None)
                adaptation.append(dict(learner=learner,budget=budget,side=side,
                    selected_index=selection['selected_index'],accepted_update=rebuilt['accepted_update'],
                    reason=rebuilt['reason'],output_skill=rebuilt['skill'],validation=validation))
    return dict(scope='POST_HOC_DESCRIPTION_OF_EXISTING_PILOT',formal_result_eligible=False,
        caveat='Selected two accepted source runs to explain their observed outcomes; not an unbiased estimate of population effects or a new test.',
        groups=groups,target_adaptation=adaptation)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Use a new output')
    result=analyze(args.suite.resolve())
    write_json(args.output,result)
    print(json.dumps([{k:v for k,v in g.items() if k not in ('measurements','skill')} for g in result['groups']]))
