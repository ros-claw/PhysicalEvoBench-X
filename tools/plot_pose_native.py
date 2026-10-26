"""Fixed-coverage native diagnostic figures; no selection by outcome."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from physicalevobench_x.core.hashing import file_digest,write_json


def load_trace(path):
    frames=[json.loads(line)['observation'] for line in path.read_text().splitlines()]
    times=np.array([o['sim_time_s'] for o in frames])
    xyz=np.array([o['object_pose_w']['position_m'] for o in frames])
    q=np.array([o['object_pose_w']['quaternion_xyzw'] for o in frames]);q/=np.linalg.norm(q,axis=1)[:,None]
    # Independent vector calculation of the candidate's fixed 0.1 s pose path window.
    steps=np.diff(times)
    if not np.allclose(steps,.005,atol=1e-9,rtol=0):raise ValueError('Expected retained 200 Hz physics trace')
    segments=2*np.arccos(np.clip(np.abs(np.sum(q[1:]*q[:-1],axis=1)),0,1))
    linear=np.linalg.norm(np.diff(xyz,axis=0),axis=1)
    angular_window=np.r_[np.full(20,np.nan),np.convolve(segments,np.ones(20),mode='valid')/.1]
    linear_window=np.r_[np.full(20,np.nan),np.convolve(linear,np.ones(20),mode='valid')/.1]
    native=np.linalg.norm([o['object_angular_velocity_w'] for o in frames],axis=1)
    baseline=xyz[np.argmin(abs(times-.5)),2]
    return times,xyz[:,2]-baseline,native,angular_window,linear_window


def plot(study,output):
    report=json.loads((study/'report.json').read_text());audit=json.loads((study/'trace_audit.json').read_text())
    if audit['status']!='TRACE_RECOMPUTATION_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Matching completed trace audit required')
    if output.exists():raise ValueError('Figure destination exists')
    output.mkdir(parents=True)
    provenance={};traces={}
    for r in report['results']:
        path=study/r['body']/r['scenario']/'physics_trace.jsonl'
        if file_digest(path)!=r['evidence_files'][str(path)]:raise ValueError('Plot source changed')
        traces[(r['body'],r['scenario'])]=load_trace(path);provenance[str(path)]=file_digest(path)
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,4,figsize=(12,5),sharex=True,sharey=True,constrained_layout=True)
    for row,body in enumerate(('franka_panda','franka_robotiq')):
        for col,scenario in enumerate(('nominal','toss','release','oscillate')):
            ax=axes[row,col];t,lift,*_=traces[(body,scenario)]
            ax.plot(t-.5,lift*1000,color='#246a87',lw=1.2)
            ax.axhline(80,color='#a33e31',ls='--',lw=.8)
            r=next(r for r in report['results'] if r['body']==body and r['scenario']==scenario)
            score=' / '.join('accept' if r[k]['task_success'] else 'reject' for k in ('candidate_50hz','candidate_200hz'))
            ax.set_title(f"{body.removeprefix('franka_')} / {scenario}\n50 / 200 Hz: {score}")
            ax.grid(alpha=.2);ax.set_xlim(0,15)
            if row==1:ax.set_xlabel('Task time (s)')
            if col==0:ax.set_ylabel('Object lift (mm)')
    fig.suptitle('All eight fixed native controls — development measurement checks')
    for ext in ('png','svg','pdf'):fig.savefig(output/f'native_controls.{ext}',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,6),sharex=True,constrained_layout=True)
    for row,body in enumerate(('franka_panda','franka_robotiq')):
        t,_,_,_,linear=traces[(body,'oscillate')]
        path=study/body/'oscillate/physics_trace.jsonl'
        xyz=np.array([json.loads(line)['observation']['object_pose_w']['position_m'] for line in path.read_text().splitlines()])
        axes[row,0].plot(t-.5,(xyz[:,0]-xyz[np.argmin(abs(t-.5)),0])*1000,lw=1.)
        axes[row,0].set_ylabel(f"{body.removeprefix('franka_')} x change (mm)")
        axes[row,1].plot(t-.5,linear,lw=1.);axes[row,1].axhline(.03,color='#a33e31',ls='--',lw=.8)
        axes[row,1].set_ylabel('Position path / 0.1 s (m/s)')
    for ax in axes.flat:ax.grid(alpha=.2);ax.set_xlim(0,15)
    for ax in axes[-1]:ax.set_xlabel('Task time (s)')
    fig.suptitle('Both fixed oscillation controls: observed object motion and path-speed threshold')
    for ext in ('png','svg','pdf'):fig.savefig(output/f'oscillation_controls.{ext}',dpi=160)
    plt.close(fig)
    key=('franka_robotiq','development_disagreement');t,lift,native,angular,linear=traces[key]
    fig,axes=plt.subplots(3,1,figsize=(9,7),sharex=True,constrained_layout=True)
    axes[0].plot(t-.5,lift*1000,label='Observed object lift');axes[0].axhline(80,color='#a33e31',ls='--',lw=.8)
    axes[0].set_ylabel('Lift (mm)')
    axes[1].plot(t-.5,native,label='PhysX-reported angular speed',lw=1.)
    axes[1].plot(t-.5,angular,label='Observed pose path / 0.1 s window',lw=1.)
    axes[1].axhline(.5,color='#a33e31',ls='--',lw=.8);axes[1].set_ylabel('Angular speed (rad/s)')
    axes[2].plot(t-.5,linear,label='Observed position path / 0.1 s window')
    axes[2].axhline(.03,color='#a33e31',ls='--',lw=.8);axes[2].set_ylabel('Path speed (m/s)');axes[2].set_xlabel('Task time (s)')
    for ax in axes:ax.grid(alpha=.2);ax.legend(loc='upper right');ax.set_xlim(0,15)
    fig.suptitle('Previously selected development case — v1 rerun: both judges accept')
    for ext in ('png','svg','pdf'):fig.savefig(output/f'development_disagreement.{ext}',dpi=160)
    plt.close(fig)
    with (output/'cases.csv').open('w') as stream:
        writer=csv.writer(stream,lineterminator='\n');writer.writerow(['body','scenario','candidate_50hz_success','candidate_200hz_success','native_50hz_success','candidate_50hz_completion_s','candidate_200hz_completion_s','stimulus_confirmed','validation_passed'])
        for r in report['results']:
            a,b,c=(r[k] for k in ('candidate_50hz','candidate_200hz','native_50hz'))
            writer.writerow([r['body'],r['scenario'],a['task_success'],b['task_success'],c['task_success'],a['completion_time_s'],b['completion_time_s'],r['stimulus_confirmed'],r['passed']])
    write_json(output/'manifest.json',dict(formal_result_eligible=False,source_report_sha256=file_digest(study/'report.json'),
        audit_sha256=file_digest(study/'trace_audit.json'),tool_sha256=file_digest(__file__),source_files=provenance,
        artifacts={p.name:file_digest(p) for p in output.iterdir()},
        caveat='All eight predefined controls plus one explicitly post-hoc selected development case; no formal pilot rescoring.'))


def plot_preparation(study,output):
    report=json.loads((study/'report.json').read_text());audit=json.loads((study/'trace_audit.json').read_text())
    comparison=json.loads((study/'preparation_comparison.json').read_text())
    if (audit['status']!='TRACE_RECOMPUTATION_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json')
        or comparison['source_report_sha256']!=file_digest(study/'report.json')):raise ValueError('Matched trace audit and comparison required')
    if output.exists():raise ValueError('Figure destination exists')
    output.mkdir(parents=True);provenance={}
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axes=plt.subplots(3,2,figsize=(12,8),sharex=True,sharey='row',constrained_layout=True)
    for col,name in enumerate(('matched_original_settle','fixed_tcp_settle')):
        r=next(r for r in report['results'] if r['scenario']==name)
        path=study/'franka_robotiq'/name/'physics_trace.jsonl'
        if file_digest(path)!=r['evidence_files'][str(path)]:raise ValueError('Preparation plot source changed')
        provenance[str(path)]=file_digest(path);t,lift,native,angular,linear=load_trace(path)
        axes[0,col].plot(t-.5,lift*1000);axes[0,col].axhline(80,color='#a33e31',ls='--',lw=.8)
        old='accept' if r['native_50hz']['task_success'] else 'reject'
        new='accept' if r['candidate_50hz']['task_success'] else 'reject'
        label='Original zero relative action' if col==0 else 'Fixed initial TCP reference'
        axes[0,col].set_title(f'{label}\nNative: {old}; candidate: {new}')
        axes[1,col].plot(t-.5,native,label='PhysX-reported angular speed',lw=1.)
        axes[1,col].plot(t-.5,angular,label='Pose path / 0.1 s window',lw=1.)
        axes[1,col].axhline(.5,color='#a33e31',ls='--',lw=.8);axes[1,col].legend(loc='upper right')
        axes[2,col].plot(t-.5,linear);axes[2,col].axhline(.03,color='#a33e31',ls='--',lw=.8)
        axes[2,col].set_xlabel('Task time (s)')
    for ax in axes.flat:ax.grid(alpha=.2);ax.set_xlim(0,15)
    axes[0,0].set_ylabel('Lift (mm)');axes[1,0].set_ylabel('Angular speed (rad/s)');axes[2,0].set_ylabel('Position path / 0.1 s (m/s)')
    fig.suptitle('One selected development condition: only the initial 0.5 s arm action differs')
    for ext in ('png','svg','pdf'):fig.savefig(output/f'preparation_comparison.{ext}',dpi=160)
    plt.close(fig)
    write_json(output/'manifest.json',dict(formal_result_eligible=False,source_report_sha256=file_digest(study/'report.json'),
        audit_sha256=file_digest(study/'trace_audit.json'),comparison_sha256=file_digest(study/'preparation_comparison.json'),
        tool_sha256=file_digest(__file__),source_files=provenance,artifacts={p.name:file_digest(p) for p in output.iterdir()},
        caveat='Two controlled reruns of a single post-hoc selected development condition; no population or transfer-effect estimate.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--mode',choices=['controls','preparation'],default='controls')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    (plot if args.mode=='controls' else plot_preparation)(args.study.resolve(),args.output.resolve())
