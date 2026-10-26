"""Validate fresh-install provenance and actual native smoke records, not exit codes alone."""
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
from reproduce_native_install_v2 import verify,assets,incompatible_lines
from physicalevobench_x.core.hashing import file_digest,write_json
from physicalevobench_x.core.schemas import ObservationFrame,EpisodeResult,SkillSpec
from physicalevobench_x.sim.judge import StableLiftJudge,robot_hard_failures
from physicalevobench_x.control.geometry import rotate

ROOT=Path(__file__).resolve().parents[1]


def result_matches(terminal,result):
    serialized=result.model_dump(mode='json')
    return all(terminal[k]==serialized[k] for k in terminal)


def replay_native(initial,frames,limits):
    judge=StableLiftJudge();judge.reset(initial)
    for obs in frames:
        if obs.sim_time_s<initial.sim_time_s:continue
        radius=sum(abs(rotate(obs.object_pose_w.quaternion_xyzw,np.eye(3)[i])[2])*obs.object_size_m[i]/2 for i in range(3))
        judge.update(obs,static_support_clear=obs.object_pose_w.position_m[2]-radius>.01,
            hard_failures=robot_hard_failures(obs,limits))
    return judge.terminal


def audit(directory,output):
    plan=verify(directory);report=json.loads((directory/'report.json').read_text());status=json.loads((directory/'status.json').read_text())
    if report['status']!='FRESH_NATIVE_INSTALL_AND_SMOKE_COMMANDS_COMPLETE' or report['plan_hash']!=plan['plan_hash']:
        raise ValueError('Fresh installation incomplete')
    if status['status']!=report['status'] or status['stages']!=report['stages']:raise ValueError('Installation stage log mismatch')
    required=['clone','checkout','arena_source','lab_transport','gr00t_transport','upstream_source','uv_sync','install_project',
              'cpu_tests','metadata_check','import_provenance','franka_panda_smoke','franka_robotiq_smoke']
    if [r['stage'] for r in report['stages']]!=required:raise ValueError('Unexpected/missing installation stages')
    for stage in report['stages']:
        path=directory/(stage['stage']+'.log')
        if stage['status']!='COMPLETE' or file_digest(path)!=stage['log_sha256'] or report['files'][str(path)]!=file_digest(path):
            raise ValueError('Installation stage log changed')
    project=directory/'project';arena=project/'third_party/IsaacLab-Arena';environment=arena/'.venv'
    if environment.is_symlink():raise ValueError('Reproduction cannot link an existing virtual environment')
    source_shas={}
    for name,path,expected in [('project',project,plan['project_commit']),('arena',arena,plan['arena_commit']),('lab',arena/'submodules/IsaacLab',plan['lab_commit'])]:
        actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
        if actual!=expected:raise ValueError('Fresh source revision changed')
        if subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=path,text=True).strip():raise ValueError('Fresh tracked source modified')
        source_shas[name]=actual
    provenance=json.loads((directory/'import_provenance.log').read_text())
    if provenance!=report['provenance'] or provenance['prefix']!=str(environment):raise ValueError('Fresh interpreter provenance mismatch')
    if any(not Path(p).is_relative_to(project) for p in provenance['import_paths'].values()):raise ValueError('Module imported outside new checkout')
    if any(not Path(p).is_relative_to(project) for p in provenance['editable_source_roots'].values()):raise ValueError('Editable source outside new checkout')
    exceptions=incompatible_lines((directory/'metadata_check.log').read_text())
    if len(exceptions)!=7 or exceptions!=incompatible_lines((ROOT/'evidence/native/package_check.log').read_text()):
        raise ValueError('Fresh dependency review does not match retained exceptions')
    assets_verified=assets(plan,project)
    if report['shared_assets_verified_before']!=483 or report['shared_assets_verified_after']!=assets_verified or assets_verified!=483:
        raise ValueError('Asset verification coverage changed')
    results=[];evidence={}
    for body in ('franka_panda','franka_robotiq'):
        path=directory/body/'episode_results.jsonl';records=[EpisodeResult.model_validate_json(l) for l in path.read_text().splitlines()]
        if len(records)!=1:raise ValueError('Exactly one native smoke episode required per body')
        r=records[0]
        if r.backend!='physx' or r.infra_failure or r.split!='dev' or r.phase!='calibration' or r.skill_hash!=SkillSpec.initial().semantic_hash:
            raise ValueError('Native smoke identity mismatch')
        trajectory=Path(r.trajectory_path)
        if file_digest(trajectory)!=r.trajectory_sha256:raise ValueError('Fresh native trajectory changed')
        metadata=trajectory.with_suffix('.json');m=json.loads(metadata.read_text())
        trace=trajectory.with_name(r.episode_id+'_trace.jsonl')
        frames=[ObservationFrame.model_validate(json.loads(l)['observation']) for l in trace.read_text().splitlines()]
        terminal=ObservationFrame.model_validate(m['terminal']['observation'])
        if terminal.sim_time_s>frames[-1].sim_time_s:frames.append(terminal)
        rescored=replay_native(ObservationFrame.model_validate(m['initial']),frames,m['effective_robot']['joint_position_limits'])
        if rescored!=m['terminal']['result'] or not result_matches(rescored,r):raise ValueError('Fresh native score replay mismatch')
        condition=m['condition']
        if (m['embodiment']!=body or condition['offset_xy_m']!=[0.,0.] or condition['yaw_rad']!=0. or condition['mass_kg']!=.2
            or not np.allclose(m['mass_readback_kg'],.2,atol=1e-5)):raise ValueError('Nominal reset configuration mismatch')
        for item in [path,trajectory,metadata,trace]:evidence[str(item)]=file_digest(item)
        results.append(dict(body=body,result=r.model_dump(),frozen_native_score_replay_matched=True))
    passed=all(x['result']['task_success'] for x in results)
    result=dict(status='FRESH_NATIVE_DEPENDENCY_REPRODUCTION_PASSED' if passed else 'FRESH_NATIVE_DEPENDENCY_REPRODUCTION_FAILED',
        formal_result_eligible=False,scope=plan['scope'],plan_hash=plan['plan_hash'],source_shas=source_shas,
        new_virtual_environment=str(environment),core_import_paths=provenance['import_paths'],
        editable_source_roots=provenance['editable_source_roots'],packages=provenance['packages'],
        shared_cached_assets_and_new_package_resources_verified=assets_verified,metadata_exceptions=exceptions,
        native_physical_calls=2,results=results,costs=dict(sim_time_s=sum(x['result']['sim_time_s'] for x in results),
            episode_wall_time_s=sum(x['result']['wall_time_s'] for x in results),installation_and_smoke_wall_time_s=report['wall_time_s']),
        source_report_sha256=file_digest(directory/'report.json'),evidence_files=evidence,
        audit_tools={p.name:file_digest(p) for p in [Path(__file__),ROOT/'tools/reproduce_native_install_v2.py']},
        limitations=['One nominal case per body, not an independent rerun of the complete pilot.',
            'Shared host, warm download cache and absolute asset cache; not independent-machine or cold-network reproduction.',
            'Seven scoped metadata exceptions remain; optional policy/teleoperation/Newton paths are untested.'])
    if output.exists():raise ValueError('Audit destination exists')
    write_json(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=audit(args.directory.resolve(),args.output.resolve());print(json.dumps(dict(status=r['status'],native_physical_calls=2)))
