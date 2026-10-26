"""Archive every development cell and export a fixed complete-matrix scientific figure."""
import argparse
import csv
import json
from pathlib import Path
import shutil
from physicalevobench_x.core.hashing import file_digest,write_json

ROOT=Path(__file__).resolve().parents[1]


def build(study,archive):
    plan=json.loads((study/'plan.json').read_text());report=json.loads((study/'report.json').read_text())
    audit=json.loads((study/'trace_audit.json').read_text())
    if audit['status']!='CALIBRATION_TRACE_AUDIT_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Matching completed trace audit required')
    archive.mkdir(parents=True,exist_ok=False)
    for name in ('plan.json','report.json','trace_audit.json','supervisor.json'):shutil.copyfile(study/name,archive/name)
    rows=[];effects=[]
    for c in audit['cases']:
        row={k:c[k] for k in ('body','scenario','condition','variant','repeat_of')}
        row.update(max_lift_m=c['macro_motion']['max_lift_m'],safety_stop=c['safety_stop'],full_horizon=c['clocks']['full_horizon'])
        for key in ('candidate_50hz','candidate_200hz','native_50hz'):
            row[key+'_success']=c['outcomes'][key]['task_success']
            row[key+'_time_s']=c['outcomes'][key]['completion_time_s']
        rows.append(row)
    for r in rows:
        if r['repeat_of'] or r['variant']=='initial':continue
        base=next(x for x in rows if x['body']==r['body'] and x['condition']==r['condition'] and x['variant']=='initial' and not x['repeat_of'])
        effects.append(dict(body=r['body'],condition=r['condition'],variant=r['variant'],
            candidate_200hz_success_difference=int(r['candidate_200hz_success'])-int(base['candidate_200hz_success']),
            candidate_200hz_completion_difference_s=(r['candidate_200hz_time_s']-base['candidate_200hz_time_s']
                if r['candidate_200hz_success'] and base['candidate_200hz_success'] else None),
            interpretation='One fixed paired trial, descriptive; no significance or learner estimate'))
    with (archive/'all_cases.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    summary=dict(status=audit['status'],formal_result_eligible=False,completed_calls=len(rows),costs=audit['costs'],
        rate_disagreements=audit['rate_disagreements'],effects=effects,repeats=audit['repeats'],
        all_tall_repeats_exact=all(r['control']['exactly_equal'] and r['physics']['exactly_equal'] for r in audit['repeats']),
        cases=rows,limitations=audit['limitations'],source_report_sha256=file_digest(study/'report.json'),
        plan_hash=plan['plan_hash'],
        realized_stages=[dict(body=c['body'],scenario=c['scenario'],stage_counts=c['executor_stage_counts']) for c in audit['cases']],
        cost_scope='Episode wall time is scene construction through last result capture, before teardown; supervisor logs separately retain process wall time.')
    write_json(archive/'summary.json',summary)
    lines=['# 开发分布校准 v1：完整实际结果','',
        f"完成 {len(rows)}/{plan['planned_calls']} 次真实 PhysX 调用；离线审计 `{audit['status']}`；`formal_result_eligible=false`。",'',
        f"候选 50/200 Hz 分类分歧 {audit['rate_disagreements']}；细高条件六对重复轨迹全部精确一致：{summary['all_tall_repeats_exact']}。",'',
        '| 本体 | 条件 | 技能 | 候选 50 Hz | 候选 200 Hz | 旧判据 | 最大抬升 m |',
        '|---|---|---|---|---|---|---|']
    for r in rows:
        labels=['成功' if r[k+'_success'] else '失败' for k in ('candidate_50hz','candidate_200hz','native_50hz')]
        lines.append(f"| {r['body']} | {r['condition']}{' (重复)' if r['repeat_of'] else ''} | {r['variant']} | {' | '.join(labels)} | {r['max_lift_m']:.4f} |")
    lines+=['','## 执行阶段与解释','',
        '失败回合不能仅凭分数解释：下面列出其真实阶段及最大抬升。抓取高度同时影响接近和下降目标，不能直接把效果归因于夹持质量。慢抬升参数只有到达 LIFT 后才被消费；未进入 LIFT 的回合不能检验抬升参数敏感性。','']
    for c in audit['cases']:
        if not c['outcomes']['candidate_200hz']['task_success']:
            lines.append(f"- {c['body']} / {c['scenario']}: {c['executor_stage_counts']}；最大抬升 {c['macro_motion']['max_lift_m']:.6f} m。")
    lines+=['','这些是固定技能的开发比较，不是学习或迁移实验。联合压力条件不能分解各物理因素的因果作用。',
        '候选成功表示首次满足判据；留存完整时段不表示成功后始终稳定。原始轨迹位于运行目录，公开归档包含逐回合结果、计划、哈希和离线重算。',
        f"总观察仿真时间 {audit['costs']['observed_sim_time_s']:.2f} s；累计回合壁钟（建场景至捕获最终结果，不含 teardown） {audit['costs']['episode_wall_time_s']:.2f} s（共享 GPU，不作为吞吐基准）。",'']
    (archive/'report.zh-CN.md').write_text('\n'.join(lines))
    plot(rows,archive)
    plot_trajectories(study,audit,archive)
    write_json(archive/'archive_manifest.json',dict(formal_result_eligible=False,
        files={str(p.relative_to(archive)):file_digest(p) for p in archive.rglob('*') if p.is_file()}))
    return summary


def plot(rows,archive):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    fig,axes=plt.subplots(1,2,figsize=(13.8,8.1))
    variants=['initial','high_grasp','slow_lift'];conditions=['nominal','tall_narrow','wide','heavy_low_friction','tall_narrow_repeat']
    for ax,body in zip(axes,['franka_panda','franka_robotiq']):
        data=np.zeros((5,3));grid={}
        for i,c in enumerate(conditions):
            for j,v in enumerate(variants):
                r=next(r for r in rows if r['body']==body and r['variant']==v and
                    (r['repeat_of'] is not None if c.endswith('_repeat') else r['repeat_of'] is None) and
                    r['condition']==c.replace('_repeat',''))
                data[i,j]=r['candidate_200hz_success'];grid[i,j]=r
        ax.imshow(data,cmap=ListedColormap(['#f3d6d4','#d2e8d8']),vmin=0,vmax=1,aspect='auto')
        ax.set_xticks(range(3),['Initial','High grasp','Slow lift']);ax.set_yticks(range(5),
            ['Nominal','Tall / narrow','Wide','Heavy / low friction','Tall repeat'])
        ax.tick_params(axis='both',length=0,pad=9)
        ax.set_title(body.replace('franka_','').title(),pad=14)
        for (i,j),r in grid.items():
            labels='/'.join('S' if r[k+'_success'] else 'F' for k in ('candidate_50hz','candidate_200hz','native_50hz'))
            time=f"{r['candidate_200hz_time_s']:.3f} s" if r['candidate_200hz_success'] else 'no success'
            ax.text(j,i,f"{labels}\n{time}\nlift {r['max_lift_m']:.3f} m",ha='center',va='center',fontsize=10.5,linespacing=1.5)
        ax.set_xticks(np.arange(-.5,3,1),minor=True);ax.set_yticks(np.arange(-.5,5,1),minor=True)
        ax.grid(which='minor',color='white',linewidth=3);ax.tick_params(which='minor',bottom=False,left=False)
    fig.suptitle('Development distribution calibration: all 30 physical trials',fontsize=16,y=.97)
    fig.text(.5,.905,'Cell labels: candidate 50 Hz / candidate 200 Hz / legacy 50 Hz (S = success, F = failure)',ha='center',fontsize=10.5)
    fig.text(.5,.035,'Color: candidate 200 Hz first success. Time: task-relative first success; lift: maximum after settling.\nFixed skills; one trial per cell plus tall repeats. No learner, transfer or population estimate.',ha='center',fontsize=10)
    fig.subplots_adjust(left=.105,right=.98,bottom=.13,top=.85,wspace=.36)
    for ext in ('png','svg','pdf'):fig.savefig(archive/('all_cases.'+ext),dpi=170)
    plt.close(fig)


def plot_trajectories(study,audit,archive):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(4,2,figsize=(12,11),sharex=True,sharey=True)
    colors=dict(initial='#3569a5',high_grasp='#b15d1c',slow_lift='#428553')
    conditions=['nominal','tall_narrow','wide','heavy_low_friction']
    for i,condition in enumerate(conditions):
        for j,body in enumerate(['franka_panda','franka_robotiq']):
            ax=axes[i,j]
            for case in audit['cases']:
                if case['body']!=body or case['condition']!=condition:continue
                path=study/body/case['scenario']/'control_trace.jsonl'
                obs=[json.loads(line)['observation'] for line in path.read_text().splitlines()]
                t=np.array([o['sim_time_s'] for o in obs]);z=np.array([o['object_pose_w']['position_m'][2] for o in obs])
                initial=np.flatnonzero(abs(t-.5)<1e-9)[0];lift=z-z[initial]
                ax.plot(t[initial:]-.5,lift[initial:],color=colors[case['variant']],
                    linestyle='--' if case['repeat_of'] else '-',linewidth=1.6,alpha=.9,
                    label=case['variant'].replace('_',' ') if not case['repeat_of'] else None)
            ax.axhline(.08,color='#555555',linestyle=':',linewidth=1)
            ax.set_title(body.replace('franka_','').title()+' / '+condition.replace('_',' '),fontsize=11)
            ax.set_xlim(0,15);ax.set_ylim(-.18,.2);ax.grid(alpha=.2)
            if j==0:ax.set_ylabel('Object lift (m)')
            if i==3:ax.set_xlabel('Task elapsed time (s)')
    axes[0,0].legend(loc='upper left',fontsize=8)
    fig.suptitle('Full retained height trajectories: every skill and condition',fontsize=15)
    fig.text(.5,.015,'Dotted: 8 cm lift requirement. Dashed: predeclared tall repeats (may overlap). Height alone is not stable-lift success.\nDevelopment only; complete observations include task failures and measured safety stops.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.055,1,.965])
    for ext in ('png','svg','pdf'):fig.savefig(archive/('height_trajectories.'+ext),dpi=170)
    plt.close(fig)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True)
    a=ap.parse_args();s=build(a.study.resolve(),a.archive.resolve());print(json.dumps(dict(status=s['status'],calls=s['completed_calls'])))
