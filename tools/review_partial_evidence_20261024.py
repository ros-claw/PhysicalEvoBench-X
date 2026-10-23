"""Read-only audit of the named interrupted pilot; writes an aggregate review snapshot.

Run from repository root with .venv312/bin/python. This is an engineering
consistency check, not a completed-suite audit or independent physics replication.
"""
import sys,json,pathlib,collections,datetime
sys.path.insert(0,str(pathlib.Path('scripts').resolve()))
from physicalevobench_x.core.hashing import file_digest,digest
from physicalevobench_x.core.schemas import EpisodeResult,SkillSpec,ObservationFrame
from physicalevobench_x.protocol.learning import reconstruct
from physicalevobench_x.sim.judge import StableLiftJudge,robot_hard_failures
from physicalevobench_x.control.geometry import rotate
from pilot_suite import execution_inputs
import numpy as np
root=pathlib.Path.cwd(); run=root/'runs/complete-v2-20261023'; suite=run/'pilot'
load=lambda p:json.loads(p.read_text())
report={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'READ_ONLY_PARTIAL_EVIDENCE_REVIEW','formal_result_eligible':False,'errors':[]}
checked={}
def check(path,expected):
 p=pathlib.Path(path)
 if not p.is_absolute():p=root/p
 if str(p) not in checked:checked[str(p)]=file_digest(p)
 assert checked[str(p)]==expected, 'Hash mismatch: '+str(p)
frozen=load(run/'freeze.json');assert frozen['freeze_hash']==digest({k:v for k,v in frozen.items() if k!='freeze_hash'})
for p,h in frozen['files'].items():check(p,h)
for name,h in frozen['gpu_evidence'].items():
 p=root/frozen['config']['gpu_evidence'][name];check(p,h);d=load(p)
 assert d['status']=='GPU_VERIFIED' and d['frozen_inputs']==frozen['files']
 for p,h in d['evidence_files'].items():check(p,h)
for body,h in frozen['development_reviews'].items():check(root/frozen['config']['development_validation_evidence'][body],h)
report['gpu_acceptance_checks']=len(frozen['gpu_evidence'])
plan=load(suite/'plan.json');assert execution_inputs(root)==plan['execution_inputs'];report['execution_inputs_unchanged']=True
report['freeze_hash']=frozen['freeze_hash'];report['planned_packages']=len(plan['packages']);report['completed_packages']=0
report['packages']=[]; total=collections.Counter();rejudge_count=0
for info in plan['packages']:
 package=suite/'packages'/info['package_id']
 if not package.exists():continue
 check(info['conditions_path'],info['conditions_sha256']); manifest=load(pathlib.Path(info['conditions_path']))
 cmap={c['condition_id']:c for cs in manifest.values() for c in cs};assert len(cmap)==sum(map(len,manifest.values()))
 item={'package':info['package_id'],'stages':{},'complete':(package/'summary.json').exists()};report['completed_packages']+=int(item['complete'])
 for cp in package.glob('stages/*/complete.json'):
  d=load(cp);assert d['identity']==dict(package=info,execution_inputs_hash=digest(plan['execution_inputs']))
  for p,h in d['files'].items():check(p,h)
  out=pathlib.Path(d['output']);item['stages'][cp.parent.name]={'complete':True}
  if (out/'candidates.jsonl').exists():
   rebuilt=reconstruct(out);sel=load(out/'selection.json');assert all(rebuilt[k]==sel[k] for k in ['accepted_update','reason','selected_index'])
   rows={r['episode_id']:r for r in map(json.loads,(out/'episode_results.jsonl').read_text().splitlines())}
   item['stages'][cp.parent.name]['selection']={k:sel[k] for k in ['accepted_update','reason','selected_index']}
   item['stages'][cp.parent.name]['validation_successes']={side:sum(rows[k]['task_success'] for k in sel['validation_'+side]) for side in ('before','candidate')}
  if (out/'summary.json').exists():item['stages'][cp.parent.name]['paired_summary']=load(out/'summary.json')
 ids=set(); stages=collections.defaultdict(list)
 for jp in sorted(package.glob('stages/*/journal/physical/[0-9]*.json')):
  d=load(jp);total['journal_entries']+=1
  if d['status']!='COMPLETE':total['unresolved_calls']+=1;continue
  total['completed_physical_calls']+=1;req=d['request'];r=EpisodeResult.model_validate(d['result'])
  assert d['request_hash']==digest(req) and req['condition']==cmap[r.condition_id]
  assert r.backend=='physx' and r.skill_hash==SkillSpec.model_validate(req['skill']).semantic_hash
  assert r.phase==req['phase'] and r.candidate_index==req['candidate_index'] and r.attempt_index==req['attempt_index']
  assert r.episode_id not in ids;ids.add(r.episode_id);stages[jp.parents[2].name].append(r)
  if r.infra_failure:total['infrastructure_failures']+=1;continue
  check(r.trajectory_path,r.trajectory_sha256)
  trace=pathlib.Path(r.trajectory_path).with_name(r.episode_id+'_trace.jsonl');meta=load(pathlib.Path(r.trajectory_path).with_suffix('.json'))
  judge=StableLiftJudge();judge.reset(ObservationFrame.model_validate(meta['initial']))
  limits=meta['effective_robot']['joint_position_limits'];initial_t=meta['initial']['sim_time_s']
  def update(o):
   q=o.object_pose_w.quaternion_xyzw;radius=sum(abs(rotate(q,np.eye(3)[i])[2])*o.object_size_m[i]/2 for i in range(3))
   return judge.update(o,hard_failures=robot_hard_failures(o,limits),static_support_clear=o.object_pose_w.position_m[2]-radius>.01)
  for line in trace.read_text().splitlines():
   o=ObservationFrame.model_validate(json.loads(line)['observation'])
   if o.sim_time_s>initial_t+1e-9:update(o)
  terminal=update(ObservationFrame.model_validate(meta['terminal']['observation']))
  assert terminal is not None,'No reconstructed terminal'
  for key in ['task_success','termination_reason','constraint_violations']:assert terminal[key]==(list(getattr(r,key)) if key=='constraint_violations' else getattr(r,key)),(r.episode_id,key)
  for key in ['completion_time_s','hold_time_s','max_lift_m']:assert abs(terminal[key]-getattr(r,key))<1e-8,(r.episode_id,key,terminal[key],getattr(r,key))
  rejudge_count+=1
 for name,rows in stages.items():
  s=item['stages'].setdefault(name,{'complete':False});s['physical_calls']=len(rows)
  if name=='source_audit' and not s['complete']:
   attempts=sorted((package/'stages'/name).glob('attempt-*/pair_attempts.jsonl'));pairs=[]
   if attempts:pairs=[json.loads(l) for l in attempts[-1].read_text().splitlines() if json.loads(l)['included']]
   lookup={r.episode_id:r for r in rows};s['partial_pair_count']=len(pairs)
   s['partial_before_successes']=sum(lookup[p['episode_ids'][0]].task_success for p in pairs)
   s['partial_after_successes']=sum(lookup[p['episode_ids'][-1]].task_success for p in pairs)
   s['warning']='Incomplete prefix; not a completed source audit or a confirmatory estimate'
 report['packages'].append(item)
report['hash_verified_files']=len(checked);report['journal_totals']=dict(total);report['recorded_episodes_rejudged_offline']=rejudge_count
report['rejudge_scope']='Replay of recorded observations through existing frozen judge; verifies recording/scoring consistency, not an independent physics replication or independent judge implementation'
report['throughput']=[{k:d[k] for k in ('embodiment','completed_episodes','successes','episode_wall')} for d in map(load,run.glob('throughput/*/throughput.json'))]
report['historical_stop_reason']='DISK_LIMIT';report['pipeline_status_at_review']=load(run/'pipeline_status.json');report['conclusion']='CONSISTENCY_REVIEW_ONLY_NO_CONFIRMED_POSITIVE_TRANSFER'
path=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else root/'runs/partial_evidence_review.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
