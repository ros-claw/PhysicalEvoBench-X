"""Explicit learner configuration and local credential loading, outside model inputs."""
import os
from pathlib import Path
import yaml
from .random_search import RandomSearch
from .bounded_llm import BoundedLLM


def load_local_credential(path=Path('.env')):
    if os.environ.get('PEBX_LLM_API_KEY') or not path.exists():
        return
    if path.stat().st_mode & 0o077:
        raise ValueError('Local credential file must have mode 0600')
    for line in path.read_text().splitlines():
        if line.startswith('PEBX_LLM_API_KEY='):
            os.environ['PEBX_LLM_API_KEY']=line.split('=',1)[1].strip()


def proposer_factory(learner, config, log_path):
    if learner=='random_search_v1':
        return RandomSearch
    if learner!='bounded_llm_v1':
        raise ValueError('Unknown learner')
    cfg=yaml.safe_load(Path(config).read_text())
    if (cfg.get('learner_id')!=learner or cfg.get('protocol')!='openai_chat_completions'
        or cfg.get('max_requests_per_candidate')!=2 or cfg.get('max_output_tokens')!=800
        or cfg.get('max_input_tokens')!=6000):
        raise ValueError('Unsupported learner protocol or budget')
    load_local_credential()
    return lambda seed:BoundedLLM(seed,endpoint=cfg['endpoint'],model=cfg['model'],log_path=log_path,
        api_key_env=cfg.get('api_key_env','PEBX_LLM_API_KEY'),timeout_s=cfg.get('request_timeout_s',60),
        reasoning_effort=cfg.get('reasoning_effort'),temperature=cfg.get('temperature',0))
