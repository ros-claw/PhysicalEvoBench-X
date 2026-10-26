"""Publish complete learning evidence without exact private scene manifests or raw states."""
import argparse
import csv
import json
from pathlib import Path
import shutil
from physicalevobench_x.core.hashing import file_digest,write_json
from physicalevobench_x.core.schemas import BOUNDS

ROOT=Path(__file__).resolve().parents[1]


def build(study,archive):
    audit=json.loads((study/'trace_audit.json').read_text());p=json.loads((study/'plan.json').read_text())
    if audit['status']!='GEOMETRY_LEARNING_TRACE_AUDIT_PASSED' or audit['source_report_sha256']!=file_digest(study/'report.json'):
        raise ValueError('Matching complete audit required')
    archive.mkdir(parents=True,exist_ok=False)
    for name in ('plan.json','report.json','supervisor.json','trace_audit.json','trace_audit.log'):
        shutil.copyfile(study/name,archive/name)
    if (study/'verification_logs').exists():shutil.copytree(study/'verification_logs',archive/'verification_logs')
    if (study/'public_plan_review.json').exists():shutil.copyfile(study/'public_plan_review.json',archive/'public_plan_review.json')
    for name in ('random_source_progress_review.json','kimi_model_progress_review.json','random_package_audit.json','random_package_audit.log','random_preparation_review.json'):
        if (study/name).exists():shutil.copyfile(study/name,archive/name)
    rows=[]
    for c in audit['cases']:
        row={k:c[k] for k in ('package_id','stage','body','episode_id','condition_id','stratum','phase','candidate_index','skill_hash','role')}
        row.update(max_observed_lift_m=c['macro_motion']['max_lift_m'],full_horizon=c['clocks']['full_horizon'],safety_stop=c['safety_stop'])
        for key,outcome in c['outcomes'].items():
            row[key+'_success']=outcome['task_success'];row[key+'_time_s']=outcome['completion_time_s']
        rows.append(row)
    with (archive/'all_physical_cases.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    summary=dict(status=audit['status'],formal_result_eligible=False,physical_calls=len(rows),source_practice_calls=20*len(audit['packages']),
        target_adaptation_calls=0,score_recomputations=audit['score_recomputation_count'],rate_disagreements=audit['rate_disagreements'],
        packages=audit['packages'],costs=audit['costs'],plan_hash=p['plan_hash'],limitations=audit['limitations'])
    write_json(archive/'summary.json',summary)
    candidates={};lines=['# 新几何任务：真实源学习与零预算迁移','',
        f"状态 `{audit['status']}`；{len(rows)} 次真实调用，{audit['score_recomputation_count']} 个评分重算；`formal_result_eligible=false`。",'',
        f"Panda→Robotiq；{len(audit['packages'])} 个提案器包，各一个源学习 seed。每组 20 回合源练习，四个源审计配对、四个目标配对；目标适配 0 回合。即使源回滚，两侧仍实际执行，成本全部保留。",'',
        '| 提案器 | 源验证接受 | 原因 | 源验证 Before→候选 | 独立源审计 Before→After | 目标 Before→After | 目标收益/退化条件数 |',
        '|---|---|---|---|---|---|---|']
    if p.get('study')=='geometry_height_coverage_source_learning_v1':
        lines.insert(4,'本包是看到两个源学习回滚后选择的高度覆盖诊断；使用全新条件，按原接受规则选择，不与原两种方法直接排名。')
    for package in audit['packages']:
        name=package['package']['package_id'];root=study/'packages'/name;dest=archive/name;dest.mkdir()
        paths={}
        for stage in ('source','source_audit','target_zero'):
            checkpoint=json.loads((root/'stages'/stage/'complete.json').read_text());out=Path(checkpoint['output']);paths[stage]=out
            stage_dest=dest/stage;stage_dest.mkdir();shutil.copyfile(root/'stages'/stage/'complete.json',stage_dest/'checkpoint.json')
            # Projection files contain condition IDs and scalar feedback, never exact scenes.
            for file in out.iterdir():
                if file.suffix in ('.json','.jsonl'):shutil.copyfile(file,stage_dest/file.name)
        shutil.copyfile(root/'artifact_freeze.json',dest/'artifact_freeze.json')
        if (root/'model_calls.jsonl').exists():shutil.copyfile(root/'model_calls.jsonl',dest/'model_calls.jsonl')
        shutil.copyfile(study/(name+'.log'),dest/'native.log')
        source=paths['source'];candidates[name]=[json.loads(l) for l in (source/'candidates.jsonl').read_text().splitlines()]
        selection=package['source_selection'];sa=package['paired']['source_audit'];ta=package['paired']['target_zero']
        lines.append(f"| {name} | {selection['accepted_update']} | {selection['reason']} | {package['source_validation']['before_successes']}/4 → {package['source_validation']['candidate_successes']}/4 | {sa['before_successes']}/4 → {sa['after_successes']}/4 | {ta['before_successes']}/4 → {ta['after_successes']}/4 | {ta['wins']} / {ta['losses']} |")
    lines+=['','上述四个配对条件仅作开发描述，不给显著性或总体效果结论。源审计与目标成绩不参与更新或回滚。','',
        '| 提案器 | 阶段 | 条件层 | Before | After |','|---|---|---|---|---|']
    null_notes=[]
    for package in audit['packages']:
        name=package['package']['package_id']
        for stage,cell in package['paired'].items():
            for family,value in cell['strata'].items():
                lines.append(f"| {name} | {stage} | {family} | {value['before_successes']}/{value['pairs']} | {value['after_successes']}/{value['pairs']} |")
        nulls=package['null_repeats']
        if nulls:
            exact=sum(x['control']['exactly_equal'] and x['physics']['exactly_equal'] for x in nulls)
            null_notes+=['',f"{name} 回滚后的真实同产物配对：{exact}/{len(nulls)} 对公开状态/实际动作精确一致。"]
    lines+=null_notes
    lines+=['','## 准备状态检查','']
    for package in audit['packages']:
        checks=package['preparation_checks'];exact=sum(c['control']['exactly_equal'] and c['physics']['exactly_equal'] for c in checks);differences={}
        for c in checks:
            for key in ('control','physics'):
                for field,value in c[key]['max_abs_numeric_differences'].items():differences[field]=max(differences.get(field,0.),value)
        lines.append(f"- {package['package']['package_id']}: 全字段精确一致 {exact}/{len(checks)}；其余已观测最大数值差 {differences}。未事后引入容差将这些标成精确一致，未改变成绩或源产物。")
    lines+=['','## 真实模型调用与成本','']
    for package in audit['packages']:
        calls=package['model_calls']
        lines.append(f"- {package['package']['package_id']}: {calls['actual_requests']} 次模型请求，{calls['valid_outputs']} 个有效输出，{calls['error_requests']} 个错误请求；provider usage {calls['usage']}，缺少 usage 的请求 {calls['usage_missing_requests']}；实际响应模型 {calls['response_models']}。")
    lines+=['',f"物理累计观察仿真时间 {audit['costs']['observed_sim_time_s']:.2f} s；累计回合壁钟 {audit['costs']['episode_wall_time_s']:.2f} s（建场景至结果捕获，不含 teardown；模型耗时另列）。",'',
        '精确条件与大型原始逐步状态留在本机运行目录，不提交私有目标 manifest。公开 CSV 保留每次真实执行、失败、安全停止、两采样频率及旧评分；source projection、模型调用、源冻结及只读重建证据可检查。',
        '完整时段轨迹不表示首次成功后始终稳定。新任务显式使用候选判据，不替换旧默认或重新标记旧成绩。',
        '本批没有无反馈提案消融，模型先验、搜索与反馈的贡献没有单独分离。完整观察成本不因首次成功而提前停止，不能从完成时间差直接声称仿真成本节省。',
        '条件层在看到校准后选定；只检验全局五维参数，尚未验证条件技能、反向、多 seed 或目标适配预算。']
    (archive/'report.zh-CN.md').write_text('\n'.join(lines)+'\n')
    plot_source(audit,candidates,archive);plot_pairs(audit,archive);plot_target_traces(study,audit,archive)
    # Defense against accidentally copying evaluator-owned exact condition objects.
    for file in archive.rglob('*'):
        if file.suffix not in ('.json','.jsonl'):continue
        values=[json.loads(line) for line in file.read_text().splitlines()] if file.suffix=='.jsonl' else [json.loads(file.read_text())]
        for value in values:check_public(value)
    write_json(archive/'archive_manifest.json',dict(formal_result_eligible=False,
        files={str(x.relative_to(archive)):file_digest(x) for x in archive.rglob('*') if x.is_file()}))
    return summary


def check_public(value):
    if isinstance(value,dict):
        if 'condition_id' in value and any(k in value for k in ('size_m','reset_seed','offset_xy_m')):
            raise ValueError('Refusing to publish an exact private condition')
        for item in value.values():check_public(item)
    elif isinstance(value,list):
        for item in value:check_public(item)


def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def save(fig,archive,name):
    for ext in ('png','svg','pdf'):fig.savefig(archive/(name+'.'+ext),dpi=170)
    plotting().close(fig)


def plot_source(audit,candidates,archive):
    plt=plotting();columns=len(audit['packages']);fig,axes=plt.subplots(2,columns,figsize=(6*columns,7.2),sharex='col',squeeze=False)
    labels=['Height','Clearance','Settle','Lift speed','Lift acceleration']
    for col,pkg in enumerate(audit['packages']):
        name=pkg['package']['package_id'];rows=candidates[name];top,bottom=axes[:,col]
        successes=[sum(c['outcomes']['candidate_50hz']['task_success'] for c in audit['cases'] if c['package_id']==name and c['role']=='exploration' and c['candidate_index']==i) for i in range(6)]
        top.plot(range(6),successes,'o-',color='#3569a5');top.set_ylim(-.1,2.3);top.set_yticks([0,1,2]);top.set_ylabel('Training successes / 2')
        selection=pkg['source_selection'];top.axvline(selection['selected_index'],color='#777777',linestyle=':')
        top.set_title(name.title()+f" | accepted={selection['accepted_update']}")
        for (key,(lo,hi)),label in zip(BOUNDS.items(),labels):
            bottom.plot(range(6),[(r['skill']['parameters'][key]-lo)/(hi-lo) for r in rows],'.-',label=label,alpha=.85)
        bottom.set_ylim(-.05,1.05);bottom.set_xticks(range(6));bottom.set_xlabel('Candidate index (0 = original skill)');bottom.set_ylabel('Parameter within bound [0, 1]')
        for ax in (top,bottom):ax.grid(alpha=.2)
    axes[1,-1].legend(fontsize=8,loc='upper left')
    fig.suptitle('Actual budgeted source practice:\nevery candidate and bounded parameter proposal' if columns==1 else 'Actual budgeted source practice: every candidate and bounded parameter proposal')
    fig.text(.5,.018,('Dotted: training-selected candidate; validation accepts or rolls back.\nOne learning seed; no method superiority estimate.' if columns==1 else 'Dotted: training-selected candidate; validation separately accepts or rolls back. One learning seed; no method superiority estimate.'),ha='center',fontsize=9,va='bottom')
    fig.tight_layout(rect=[0,.05,1,.95]);save(fig,archive,'source_learning')


def plot_pairs(audit,archive):
    import numpy as np
    from matplotlib.colors import ListedColormap
    plt=plotting();columns=len(audit['packages']);fig,axs=plt.subplots(1,columns,figsize=(6*columns,10.8),squeeze=False);axes=axs[0];cmap=ListedColormap(['#f3d6d4','#d2e8d8'])
    for ax,pkg in zip(axes,audit['packages']):
        name=pkg['package']['package_id'];data=np.zeros((8,2));grid={};labels=[]
        for row,case in enumerate([c for c in audit['cases'] if c['package_id']==name and c['stage'] in ('source_audit','target_zero')][::2]):
            group=[c for c in audit['cases'] if c['package_id']==name and c['stage']==case['stage'] and c['condition_id']==case['condition_id']]
            for col,role in enumerate(('before','after')):
                c=next(c for c in group if c['role']==role);data[row,col]=c['outcomes']['candidate_50hz']['task_success'];grid[row,col]=c
            labels.append(('Audit' if case['stage']=='source_audit' else 'Target')+' / '+case['stratum'].replace('_narrow','')+'\n'+case['condition_id'][:6])
        ax.imshow(data,cmap=cmap,vmin=0,vmax=1,aspect='auto');ax.set_xticks([0,1],['Before','After']);ax.set_yticks(range(8),labels)
        ax.axhline(3.5,color='#555555',linewidth=2);ax.set_title(name.title(),pad=12)
        for (row,col),case in grid.items():
            score=case['outcomes']['candidate_50hz'];time=f"{score['completion_time_s']:.2f} s" if score['task_success'] else 'no success'
            ax.text(col,row,('SUCCESS' if score['task_success'] else 'FAIL')+'\n'+time+f"\nlift {case['macro_motion']['max_lift_m']:.3f} m",ha='center',va='center',fontsize=10.5,linespacing=1.35)
        ax.tick_params(length=0,pad=7)
        ax.set_xticks(np.arange(-.5,2,1),minor=True);ax.set_yticks(np.arange(-.5,8,1),minor=True);ax.grid(which='minor',color='white',linewidth=2);ax.tick_params(which='minor',bottom=False,left=False)
    fig.suptitle('Independent paired checks after\nfreezing source artifacts' if columns==1 else 'Independent paired checks after freezing source artifacts',fontsize=14 if columns==1 else 15)
    fig.text(.5,.925 if columns==1 else .935,'Top four: source audit (Panda).\nBottom four: target evaluation (Robotiq), zero adaptation.' if columns==1 else 'Top four rows: source audit (Panda). Bottom four: target evaluation (Robotiq), zero adaptation.',ha='center',fontsize=9 if columns==1 else 10,va='center')
    fig.text(.5,.025,('Color/time: first success at 50 Hz. Lift: full trace maximum.\nAll failures retained. Four pairs; one learning seed.\nDevelopment only, no population significance estimate.' if columns==1 else 'Color/time: candidate 50 Hz first success. Lift: full retained trace maximum. All failures retained.\nFour pairs per stage and one learning seed; development only, no population significance estimate.'),ha='center',fontsize=9,va='bottom')
    fig.subplots_adjust(left=.22 if columns==1 else .12,right=.98,top=.87 if columns==1 else .9,bottom=.10 if columns==1 else .085,wspace=.5);save(fig,archive,'all_paired_cases')


def plot_target_traces(study,audit,archive):
    import numpy as np
    plt=plotting();columns=len(audit['packages']);fig,axes=plt.subplots(4,columns,figsize=(6*columns,10),sharex=True,sharey=True,squeeze=False)
    for col,pkg in enumerate(audit['packages']):
        name=pkg['package']['package_id'];cases=[c for c in audit['cases'] if c['package_id']==name and c['stage']=='target_zero']
        for row in range(4):
            ax=axes[row,col]
            for case in cases[2*row:2*row+2]:
                path=study/'packages'/name/'trajectories/target_zero'/case['episode_id']/'control_trace.jsonl'
                obs=[json.loads(l)['observation'] for l in path.read_text().splitlines()];t=np.array([o['sim_time_s'] for o in obs]);z=np.array([o['object_pose_w']['position_m'][2] for o in obs]);start=np.flatnonzero(abs(t-.5)<1e-9)[0]
                ax.plot(t[start:]-.5,z[start:]-z[start],label=case['role'].title(),linewidth=1.8)
            case=cases[2*row];ax.set_title(name.title()+' / '+case['stratum']+' / '+case['condition_id'][:6],fontsize=10)
            ax.axhline(.08,color='#555555',linestyle=':',linewidth=1);ax.set_xlim(0,15);ax.set_ylim(-.2,.2);ax.grid(alpha=.2)
            if col==0:ax.set_ylabel('Object lift (m)')
            if row==3:ax.set_xlabel('Target task elapsed time (s)')
    axes[0,0].legend(fontsize=8);fig.suptitle('Zero-budget target evaluation:\nevery before/after height trajectory' if columns==1 else 'Zero-budget target evaluation: every before/after height trajectory')
    fig.text(.5,.018,('Dotted: 8 cm lift; height alone is not stability.\nCurves may overlap. Target feedback never selected the source artifact.' if columns==1 else 'Curves may overlap. Dotted: 8 cm lift; height alone is not the stability score.\nNo target feedback was used for source selection.'),ha='center',fontsize=9,va='bottom')
    fig.tight_layout(rect=[0,.05,1,.95]);save(fig,archive,'target_height_trajectories')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True)
    a=ap.parse_args();s=build(a.study.resolve(),a.archive.resolve());print(json.dumps(dict(status=s['status'],physical_calls=s['physical_calls'])))
