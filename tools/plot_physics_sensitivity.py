"""Publish the entire physics-profile matrix and all selected-case traces."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_pose_native import load_trace
from physicalevobench_x.core.hashing import file_digest,write_json

ROOT=Path(__file__).resolve().parents[1]


def plot(study,output):
    plan=json.loads((study/'plan.json').read_text());report=json.loads((study/'report.json').read_text())
    audit=json.loads((study/'trace_audit.json').read_text())
    if audit['status']!='PHYSICS_SENSITIVITY_TRACE_AUDIT_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Complete matching trace audit required')
    if output.exists():raise ValueError('Figure destination exists')
    output.mkdir(parents=True);profiles=list(plan['profiles']);source={}
    rows=[(b,s) for b in ('franka_panda','franka_robotiq') for s in ('nominal','toss','release','oscillate')]
    rows.append(('franka_robotiq','development_disagreement'))
    results={(r['body'],r['control_scenario'],r['profile']):r for r in report['results'] if r.get('kind')!='CONFIGURATION_ONLY'}
    metrics={(r['body'],r['scenario'],r['profile']):r for r in audit['cases'] if r['kind']=='FULL_HORIZON'}
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(12,7),constrained_layout=True);ax.axis('off')
    texts=[];colours=[]
    for body,scenario in rows:
        textrow=[];colourrow=[]
        for profile in profiles:
            r=results[(body,scenario,profile)];a,b,n=(int(r[k]['task_success']) for k in ('candidate_50hz','candidate_200hz','native_50hz'))
            label='PASS' if r['passed'] else 'FAIL'
            textrow.append(f'{label}   C50/C200/N50: {a}/{b}/{n}')
            colourrow.append('#e2f0e8' if r['passed'] else '#f8dedb')
        texts.append(textrow);colours.append(colourrow)
    table=ax.table(cellText=texts,cellColours=colours,rowLabels=[b.removeprefix('franka_')+' / '+s.replace('_',' ') for b,s in rows],
        colLabels=[p.replace('_','\n') for p in profiles],cellLoc='center',loc='center',bbox=[.28,.05,.72,.88])
    table.auto_set_font_size(False);table.set_fontsize(8)
    ax.set_title('All 36 full-horizon physics controls; eight configuration-only probes are separate\nPASS/FAIL: predeclared validation; 0/1: each judge classification, not learner performance',pad=16)
    for ext in ('png','svg','pdf'):fig.savefig(output/f'profile_matrix.{ext}',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(3,4,figsize=(14,8),sharex=True,sharey='row',constrained_layout=True)
    for col,profile in enumerate(profiles):
        r=results[('franka_robotiq','development_disagreement',profile)]
        path=study/'franka_robotiq'/r['scenario']/'physics_trace.jsonl'
        if file_digest(path)!=r['evidence_files'][str(path)]:raise ValueError('Figure trace changed')
        source[str(path)]=file_digest(path);t,lift,native,angular,linear=load_trace(path)
        axes[0,col].plot(t-.5,lift*1000);axes[0,col].axhline(80,color='#a33e31',ls='--',lw=.8)
        a,b,n=(int(r[k]['task_success']) for k in ('candidate_50hz','candidate_200hz','native_50hz'))
        axes[0,col].set_title(profile.replace('_',' ')+'\n'+f'C50/C200/N50: {a}/{b}/{n}',fontsize=9)
        axes[1,col].plot(t-.5,native,lw=.8,label='PhysX-reported')
        axes[1,col].plot(t-.5,angular,lw=.8,label='Observed pose path / 0.1 s')
        axes[1,col].axhline(.5,color='#a33e31',ls='--',lw=.8)
        axes[2,col].plot(t-.5,linear,lw=.8);axes[2,col].axhline(.03,color='#a33e31',ls='--',lw=.8)
        axes[2,col].set_xlabel('Task time (s)')
    axes[0,0].set_ylabel('Lift (mm)');axes[1,0].set_ylabel('Angular speed (rad/s)');axes[2,0].set_ylabel('Position path / 0.1 s (m/s)')
    axes[1,0].legend(loc='upper right',fontsize=7)
    for ax in axes.flat:ax.grid(alpha=.2);ax.set_xlim(0,15)
    fig.suptitle('All four profiles for the same selected development case — descriptive sensitivity, no learner change')
    for ext in ('png','svg','pdf'):fig.savefig(output/f'selected_case_profiles.{ext}',dpi=160)
    plt.close(fig)
    with (output/'all_cases.csv').open('w') as stream:
        writer=csv.writer(stream,lineterminator='\n');writer.writerow(['body','scenario','profile','validation_passed','stimulus_confirmed','candidate_50hz_success','candidate_200hz_success','native_50hz_success','candidate_50hz_completion_s','candidate_200hz_completion_s','native_50hz_completion_s','final_5s_native_angular_median_radps','final_5s_pose_angular_window_median_radps','final_5s_pose_linear_window_median_mps'])
        for body,scenario in rows:
            for profile in profiles:
                r=results[(body,scenario,profile)];m=metrics[(body,scenario,profile)]['motion']
                a,b,n=(r[k] for k in ('candidate_50hz','candidate_200hz','native_50hz'))
                writer.writerow([body,scenario,profile,r['passed'],r['stimulus_confirmed'],a['task_success'],b['task_success'],n['task_success'],a['completion_time_s'],b['completion_time_s'],n['completion_time_s'],m['final_5s_native_angular_median_radps'],m['final_5s_pose_angular_window_median_radps'],m['final_5s_pose_linear_window_median_mps']])
    write_json(output/'manifest.json',dict(formal_result_eligible=False,report_sha256=file_digest(study/'report.json'),
        audit_sha256=file_digest(study/'trace_audit.json'),source_files=source,
        tools={p.name:file_digest(p) for p in [Path(__file__),ROOT/'tools/plot_pose_native.py']},
        artifacts={p.name:file_digest(p) for p in output.iterdir()},
        scope='Full predefined task matrix; one selected development case shown under every profile; no learner outcomes.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();plot(args.study.resolve(),args.output.resolve())
