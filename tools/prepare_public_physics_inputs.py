"""Materialize published development inputs for a new v3 reproduction plan, without raw runs."""
import argparse
import json
from pathlib import Path
import shutil
from physicalevobench_x.core.hashing import digest,file_digest,write_json
from physicalevobench_x.core.schemas import SkillSpec

ROOT=Path(__file__).resolve().parents[1]


def prepare(root,output):
    # v3 deliberately keeps its original execution and verification code unchanged.
    previous=root/'runs/pose-native-matched-v2-20261026'
    if previous.exists() or output.exists():raise ValueError('Use a clean checkout and new output; existing studies are never overwritten')
    source=root/'evidence/measurement/physics_sensitivity_v3/source_development_case.json'
    original_plan=root/'evidence/measurement/pose_matched_settle_v2/plan.json'
    original_report=root/'evidence/measurement/pose_matched_settle_v2/report.json'
    data=json.loads(original_plan.read_text());case=json.loads(source.read_text())
    if (data['plan_hash']!=digest({k:v for k,v in data.items() if k!='plan_hash'}) or
        data['source_disagreement']['sha256']!=file_digest(source)):raise ValueError('Published source lineage changed')
    if json.loads(original_report.read_text())['status']!='NATIVE_CANDIDATE_DIAGNOSTICS_PASSED':raise ValueError('Published prior diagnosis not complete')
    skill=data['jobs']['franka_robotiq'][0]['skill']
    if SkillSpec.model_validate(skill).semantic_hash!=case['result']['skill_hash']:raise ValueError('Published source skill mismatch')
    previous.mkdir(parents=True);output.mkdir(parents=True)
    # This is a derived input manifest, never a fabricated new physical result.
    data['source_disagreement']['path']=str(source.resolve())
    data['derived_public_reproduction_input']=dict(original_plan_sha256=file_digest(original_plan),
        scope='Path mapping for a new execution plan only; archived physical report remains original-machine evidence')
    data['plan_hash']=digest({k:v for k,v in data.items() if k!='plan_hash'})
    write_json(previous/'plan.json',data);shutil.copy2(original_report,previous/'report.json')
    fragment=dict(study='PUBLIC_SOURCE_VARIANT_INPUTS_ONLY',formal_result_eligible=False,
        variants={case['job']['variant']:skill},source_case_sha256=file_digest(source),
        scope='Published selected development inputs; contains no new physical calls or claimed results')
    fragment['plan_hash']=digest(fragment);write_json(output/'plan.json',fragment)
    result=dict(status='PUBLIC_DEVELOPMENT_INPUTS_PREPARED',formal_result_eligible=False,
        native_physical_calls=0,source_case_sha256=file_digest(source),original_prior_report_sha256=file_digest(original_report),
        derived_prior_plan_sha256=file_digest(previous/'plan.json'),source_study=str(output.resolve()))
    write_json(output/'preparation.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.root.resolve(),a.output.resolve())))
