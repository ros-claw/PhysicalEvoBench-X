"""Plot every failed After pair in one historical run; post-hoc, not a new test."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from physicalevobench_x.core.hashing import file_digest, write_json


def plot(pilot, output):
    package=pilot/'packages/bounded_llm_v1/franka_robotiq/seed-0'
    stage=Path(json.loads((package/'stages/evaluation_0/complete.json').read_text())['output'])
    pairs=[json.loads(l) for l in (stage/'pair_attempts.jsonl').read_text().splitlines()]
    records={r['episode_id']:r for r in map(json.loads,(stage/'episode_results.jsonl').read_text().splitlines())}
    failed=[p for p in pairs if p['included'] and not records[p['episode_ids'][-1]]['task_success']]
    if not failed:raise ValueError('Selected historical run has no failed After pairs')
    output.mkdir(parents=True,exist_ok=False)
    fig,axes=plt.subplots(len(failed),2,figsize=(10,2.25*len(failed)),squeeze=False,sharex=True)
    export, provenance=[],{}
    palette=[('#24649A','-','Before'),('#CA6B25','--','After')]
    for index,pair in enumerate(failed):
        for eid,(color,style,label) in zip(pair['episode_ids'],palette):
            result=records[eid]
            trajectory=Path(result['trajectory_path'])
            if file_digest(trajectory)!=result['trajectory_sha256']:raise ValueError('Trajectory changed')
            meta_path=trajectory.with_suffix('.json')
            trace=trajectory.with_name(eid+'_trace.jsonl')
            meta=json.loads(meta_path.read_text())
            initial=meta['initial']
            states=[json.loads(l)['observation'] for l in trace.read_text().splitlines()]
            terminal=meta['terminal']['observation']
            if states[-1]['sim_time_s']<terminal['sim_time_s']:states.append(terminal)
            states=[s for s in states if s['sim_time_s']>=initial['sim_time_s']]
            t=np.array([s['sim_time_s']-initial['sim_time_s'] for s in states])
            height=np.array([s['object_pose_w']['position_m'][2]-initial['object_pose_w']['position_m'][2] for s in states])
            angular=np.linalg.norm([s['object_angular_velocity_w'] for s in states],axis=1)
            elevated=height>=.08-1e-12
            # Leave gaps outside the defined elevated window, rather than joining them.
            axes[index,0].plot(t,np.where(elevated,angular,np.nan),color=color,ls=style,lw=1.4,label=label)
            axes[index,1].plot(t,height,color=color,ls=style,lw=1.4,label=label)
            for elapsed,h,a,high in zip(t,height,angular,elevated):
                export.append(dict(case=index+1,side=label,execution_time_s=elapsed,lift_m=h,
                                   object_angular_radps=a,elevated=bool(high)))
            for p in [trajectory,meta_path,trace]:provenance[str(p)]=file_digest(p)
        for col,(threshold,ylabel) in enumerate([(.5,'Reported angular speed (rad/s)'),(.08,'Lift (m)')]):
            axis=axes[index,col]
            axis.axhline(threshold,color='#555555',ls=':',lw=1.1)
            axis.set_xlim(0,15)
            axis.set_ylim(0,.75 if col==0 else .14)
            axis.set_xticks([0,3,6,9,12,15])
            axis.set_yticks([0,.25,.5,.75] if col==0 else [0,.04,.08,.12])
            axis.set_ylabel(ylabel)
            axis.grid(axis='y',color='#E5E5E5',lw=.6)
            axis.spines[['top','right']].set_visible(False)
            axis.set_title(f'Failure pair {index+1}: '+('angular speed when lift >= 0.08 m' if col==0 else 'object lift'),fontsize=10)
    axes[0,0].legend(loc='upper left',frameon=False,ncol=2)
    for axis in axes[-1]:axis.set_xlabel('Execution time (s; measured trace ends at termination)')
    fig.suptitle('Kimi Robotiq → Panda, seed 0, target budget 0\nAll failed After pairs with their matched Before traces',fontsize=13)
    fig.text(.5,.012,'Historical post-hoc description. Reported PhysX velocity can differ from pose evolution under constraints.\n'
             'Dotted lines are frozen thresholds. Five failure pairs are not five independent learning runs.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.055,1,.94))
    for suffix in ('svg','pdf','png'):fig.savefig(output/('failure_pairs.'+suffix),dpi=150)
    plt.close(fig)
    with (output/'trace_points.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(export[0]));writer.writeheader();writer.writerows(export)
    write_json(output/'manifest.json',dict(scope='POST_HOC_HISTORICAL_FAILURE_PAIRS',formal_result_eligible=False,
        selection='Every included pair whose After failed in the specified run/budget; no cherry-picked subset',
        failure_pairs=len(failed),input_files=provenance,
        outputs={p.name:file_digest(p) for p in output.iterdir() if p.is_file()}))
    return dict(failure_pairs=len(failed),output=str(output))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(plot(args.pilot,args.output)))
