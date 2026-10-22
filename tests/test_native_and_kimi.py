"""Contracts for the deployment/API failures encountered in real acceptance runs."""
import json
from pathlib import Path
import pytest
from physicalevobench_x.core.schemas import SkillSpec
from physicalevobench_x.learners.bounded_llm import BoundedLLM
from physicalevobench_x.learners.factory import load_local_credential,proposer_factory
from physicalevobench_x.reporting.calibration import recover_completed_trace


def test_kimi_uses_temperature_one_effort_and_bounded_output(tmp_path):
    requests=[]
    def transport(payload):
        requests.append(payload)
        return {'model':'k3','choices':[{'message':{'content':SkillSpec.initial().model_dump_json()}}],
                'usage':{'prompt_tokens':700,'completion_tokens':250}}
    p=BoundedLLM(0,endpoint='https://api.kimi.com/coding/v1/chat/completions',model='k3',
        log_path=tmp_path/'calls.jsonl',temperature=1,reasoning_effort='low',transport=transport)
    assert p.propose(SkillSpec.initial(),[])==SkillSpec.initial()
    assert requests[0]['temperature']==1
    assert requests[0]['reasoning_effort']=='low'
    assert requests[0]['max_tokens']==800
    audit=json.loads((tmp_path/'calls.jsonl').read_text())
    assert audit['response_model']=='k3'
    assert audit['temperature']==1


def test_local_credential_requires_private_mode_and_respects_environment(tmp_path,monkeypatch):
    monkeypatch.delenv('PEBX_LLM_API_KEY',raising=False)
    path=tmp_path/'credential'
    path.write_text('PEBX_LLM_API_KEY=test-only-value\n')
    path.chmod(0o644)
    with pytest.raises(ValueError,match='0600'):
        load_local_credential(path)
    path.chmod(0o600)
    load_local_credential(path)
    import os
    assert os.environ['PEBX_LLM_API_KEY']=='test-only-value'
    path.write_text('PEBX_LLM_API_KEY=other\n')
    load_local_credential(path)
    assert os.environ['PEBX_LLM_API_KEY']=='test-only-value'
    monkeypatch.delenv('PEBX_LLM_API_KEY',raising=False)


def test_partial_calibration_trace_cannot_be_recovered(tmp_path):
    (tmp_path/'trace.jsonl').write_text('')
    with pytest.raises(ValueError,match='incomplete'):
        recover_completed_trace(tmp_path)
    assert not (tmp_path/'calibration.json').exists()


def test_actual_kimi_config_builds_fresh_proposers(tmp_path,monkeypatch):
    monkeypatch.setenv('PEBX_LLM_API_KEY','test-only-value')
    config=Path(__file__).resolve().parents[1]/'configs/learners/kimi_k3.yaml'
    factory=proposer_factory('bounded_llm_v1',config,tmp_path/'calls.jsonl')
    a,b=factory(1),factory(1)
    assert a is not b
    assert a.temperature==b.temperature==1
    assert a.model==b.model=='k3'
