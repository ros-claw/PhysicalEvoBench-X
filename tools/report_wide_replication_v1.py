"""Archive and plot all cells of the explicitly selected wide-condition replication."""
import argparse
import json
from pathlib import Path
import shutil
from physicalevobench_x.core.hashing import file_digest,write_json


def build(study,archive):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    p=json.loads((study/'plan.json').read_text());r=json.loads((study/'report.json').read_text())
    c=json.loads((study/'comparison.json').read_text());a=json.loads((study/'trace_audit.json').read_text())
    if a['source_report_sha256']!=file_digest(study/'report.json') or a['status']!='CALIBRATION_TRACE_AUDIT_PASSED':
        raise ValueError('Matching completed replication audit required')
    archive.mkdir(parents=True,exist_ok=False)
    for name in ('plan.json','report.json','trace_audit.json','comparison.json','supervisor.json','host_gpu_inventory.csv','trace_audit.log','comparison.log','franka_robotiq.log'):
        shutil.copyfile(study/name,archive/name)
    source=Path(p['replication_source']['directory']);fig,axes=plt.subplots(1,3,figsize=(12,4.2),sharey=True)
    variants=['initial','high_grasp','slow_lift'];lines=['# 宽物体权衡复现：实际结果','',
        '明确为看到首批结果后的条件选择；同机、同 seed，GPU 1→GPU 0。全部三个技能保留，不构成盲测或总体估计。','',
        '| 技能 | 首批候选 200 Hz | 复现候选 200 Hz | 全字段评分一致 | 全状态/动作一致 |',
        '|---|---|---|---|---|']
    for ax,v in zip(axes,variants):
        case=next(x for x in c['cases'] if x['variant']==v)
        for root,label,style in [(source,'Original (GPU 1)','-'),(study,'Replication (GPU 0)','--')]:
            obs=[json.loads(line)['observation'] for line in (root/'franka_robotiq'/('wide__'+v)/'control_trace.jsonl').read_text().splitlines()]
            t=np.array([o['sim_time_s'] for o in obs]);z=np.array([o['object_pose_w']['position_m'][2] for o in obs]);start=np.flatnonzero(abs(t-.5)<1e-9)[0]
            ax.plot(t[start:]-.5,z[start:]-z[start],style,label=label,linewidth=1.8)
        ax.axhline(.08,color='#666666',linestyle=':',linewidth=1);ax.set_xlim(0,15);ax.set_ylim(-.01,.14);ax.grid(alpha=.2)
        ax.set_title(v.replace('_',' ').title());ax.set_xlabel('Task elapsed time (s)')
        before='成功' if case['source_scores']['candidate_200hz']['task_success'] else '失败'
        after='成功' if case['replication_scores']['candidate_200hz']['task_success'] else '失败'
        exact=case['control']['exactly_equal'] and case['physics']['exactly_equal']
        lines.append(f"| {v} | {before} | {after} | {case['all_score_fields_exact']} | {exact} |")
    axes[0].set_ylabel('Object lift (m)');axes[0].legend(fontsize=8)
    fig.suptitle('Post-hoc Robotiq wide-condition replication: every skill')
    fig.text(.5,.025,'Dotted: 8 cm lift requirement; source and replication curves may overlap. Authored skills, same seed; no learning or transfer claim.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.08,1,.94])
    for ext in ('png','svg','pdf'):fig.savefig(archive/('all_replications.'+ext),dpi=170)
    plt.close(fig)
    lines+=['',f"新增 {r['completed_cases']} 次真实调用，观察 {r['costs']['observed_sim_time_s']:.1f} 仿真秒；全部 9 个评分离线重算一致。",'',
        '只验证该固定开发条件下三个技能的复现；不推断参数因果接触机理、多 seed 稳健性或新经验迁移。宽条件依然是几何与摩擦的联合条件。',
        '初始与慢抬升成功、高抓取失败的现象应与细高条件的相反偏好共同保留。']
    (archive/'report.zh-CN.md').write_text('\n'.join(lines)+'\n')
    write_json(archive/'archive_manifest.json',dict(formal_result_eligible=False,
        files={str(x.relative_to(archive)):file_digest(x) for x in archive.rglob('*') if x.is_file()}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True)
    a=ap.parse_args();build(a.study.resolve(),a.archive.resolve())
