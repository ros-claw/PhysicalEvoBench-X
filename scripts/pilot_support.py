"""Crash-safe replay of completed work; an ambiguous physical call fails closed.

Only evaluator-owned storage may hold this journal. Never mount it in learners.
"""
import json
import os
from pathlib import Path
from physicalevobench_x.core.hashing import digest, write_json, file_digest
from physicalevobench_x.core.schemas import EpisodeResult, SkillSpec


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    write_json(temporary, data)
    with temporary.open('rb') as stream:
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ReplayJournal:
    def __init__(self, directory, identity):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        metadata = self.directory/'identity.json'
        if metadata.exists():
            if json.loads(metadata.read_text()) != identity:
                raise ValueError('Journal version/input identity mismatch')
        else:
            atomic_json(metadata, identity)
        self.index = 0

    def call(self, request, execute, *, physical=False):
        index = self.index
        self.index += 1
        path = self.directory/f'{index:05d}.json'
        identity = digest(request)
        if path.exists():
            record = json.loads(path.read_text())
            if record['request_hash'] != identity:
                raise ValueError('Replay request diverged; cannot reuse a different experiment')
            if record['status'] != 'COMPLETE':
                raise RuntimeError('INCOMPLETE: ambiguous in-flight call; retain evidence and reconcile before resume')
            result = record['result']
            if physical and not result.get('infra_failure'):
                trajectory = result.get('trajectory_path')
                if not trajectory or file_digest(trajectory) != result['trajectory_sha256']:
                    raise ValueError('Replayed physical trajectory missing or changed')
            return result
        atomic_json(path, dict(request_hash=identity, request=request, status='STARTED', physical=physical))
        result = execute()
        atomic_json(path, dict(request_hash=identity, request=request, status='COMPLETE', physical=physical, result=result))
        return result


class ReplayRunner:
    def __init__(self, journal, runner):
        self.journal, self.runner = journal, runner

    def run(self, **request):
        import shutil
        if shutil.disk_usage(self.journal.directory).free < 2*1024**3:
            raise RuntimeError('DISK_LIMIT: stop before starting another physical call; existing journal is resumable')
        public_request = {**request, 'skill': request['skill'].model_dump()}
        result = self.journal.call(public_request,
            lambda: self.runner.run(**request).model_dump(), physical=True)
        return EpisodeResult.model_validate(result)


def replay_factory(journal, factory):
    def create(seed):
        proposer = factory(seed)
        class ReplayProposer:
            proposals = None
            def propose(self, incumbent, history):
                request = dict(seed=seed, incumbent=incumbent.model_dump(), history=history)
                def execute():
                    error, skill = None, None
                    try:
                        skill = proposer.propose(incumbent, history).model_dump()
                    except (ValueError, TimeoutError) as exc:
                        error = type(exc).__name__
                    return dict(skill=skill, error=error,
                        rng_state=proposer.rng.getstate() if hasattr(proposer, 'rng') else None,
                        details=proposer.proposals[-1] if getattr(proposer, 'proposals', None) else None)
                result = journal.call(request, execute)
                if result.get('rng_state') is not None:
                    def tuples(value):
                        return tuple(tuples(v) for v in value) if isinstance(value, (tuple, list)) else value
                    proposer.rng.setstate(tuples(result['rng_state']))
                self.proposals = [result['details']]
                if result.get('error'):
                    raise {'ValueError': ValueError, 'TimeoutError': TimeoutError}[result['error']]('Recorded proposal error')
                return SkillSpec.model_validate(result['skill'])
        return ReplayProposer()
    return create
