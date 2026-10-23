"""Stateless OpenAI-compatible HTTP transport; no SDK, tools, or filesystem access.

Provider endpoint/model are explicit configuration, not inferred defaults.
"""
import json
import os
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error
from ..core.schemas import SkillSpec, bounds_for
from ..core.hashing import digest, append_json, canonical

PROMPT = ('Propose one complete SkillSpec JSON object for StableLift. Lift a free cuboid by 0.08 m '
          'and hold stable for 1 s. Only the five bounded physical parameters may change. '
          'Do not output rationale, code, tools, or extra fields. Parameter units are SI. ')


class BoundedLLM:
    learner_id = 'bounded_llm_v1'

    def __init__(self, seed, *, endpoint, model, log_path, api_key_env='PEBX_LLM_API_KEY', timeout_s=60, transport=None, reasoning_effort=None, temperature=0):
        self.seed, self.endpoint, self.model = seed, endpoint, model
        self.log_path, self.timeout_s, self.api_key_env = log_path, timeout_s, api_key_env
        if reasoning_effort not in (None,'low','high','max'):
            raise ValueError('Unsupported reasoning effort')
        if not 0 <= temperature <= 2:
            raise ValueError('Temperature out of range')
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.transport = transport or self._http
        self.proposals = []

    def _http(self, payload):
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ValueError('Model API credential missing')
        request = urllib.request.Request(self.endpoint, data=canonical(payload).encode(),
            headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json',
                     'User-Agent': 'physicalevobench-x/0.1 (bounded parameter proposer)'})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.load(response)

    def propose(self, incumbent, history):
        # Conservative UTF-8 byte bound: <= 6000 tokens for byte-based BPE.
        messages = [{'role': 'system', 'content': PROMPT + canonical(bounds_for(incumbent))}]
        schema = SkillSpec.model_json_schema()
        schema['properties']['controller_family'] = {'const': incumbent.controller_family}
        history = list(history)
        while True:
            content = canonical(dict(incumbent=incumbent.model_dump(), history=history,
                                     schema=schema))
            if len((messages[0]['content']+content).encode()) <= 5800:
                break
            if not history:
                raise ValueError('Fixed prompt exceeds token envelope')
            history.pop(0) # deterministic oldest-first pruning
        messages.append({'role': 'user', 'content': content})
        errors = []
        for attempt in range(2):
            payload = dict(model=self.model, temperature=self.temperature, max_tokens=800, messages=messages)
            if self.reasoning_effort is not None:
                payload['reasoning_effort'] = self.reasoning_effort
            start = time.monotonic()
            requested_at_utc=datetime.now(timezone.utc).isoformat()
            response, raw, candidate = None, None, None
            error = None
            http_status = None
            try:
                response = self.transport(payload)
                raw = response['choices'][0]['message']['content']
                candidate = SkillSpec.model_validate_json(raw)
                if candidate.controller_family != incumbent.controller_family:
                    candidate = None
                    raise ValueError('Controller family is fixed by the evaluator')
                return candidate
            except (ValueError, KeyError, IndexError, OSError, TimeoutError) as exc:
                error = type(exc).__name__
                http_status = getattr(exc,'code',None)
                errors.append(error)
            finally:
                log = dict(model=self.model, temperature=self.temperature, response_model=(response or {}).get("model"), reasoning_effort=self.reasoning_effort, endpoint=self.endpoint, seed_requested=False,
                    requested_at_utc=requested_at_utc,response_id=(response or {}).get('id'),
                    provider_created=(response or {}).get('created'),immutable_model_revision=None,
                    http_status=http_status,
                    rng_seed=self.seed, attempt=attempt, prompt_hash=digest(messages),
                    prompt=messages, response_text=raw, usage=(response or {}).get('usage'),
                    wall_time_s=time.monotonic()-start, error=error,
                    valid=candidate is not None, input_estimation='utf8_bytes_upper_bound',
                    input_estimated_upper_bound=len(canonical(messages).encode()))
                append_json(self.log_path, log)
                self.proposals.append(log)
            if attempt == 0:
                # Repair is bounded and never sends untrusted free text back as instructions.
                messages = messages[:2] + [{'role': 'user', 'content': 'Previous output invalid. Return complete JSON matching schema.'}]
        self.proposals.append(dict(fallback=True, errors=errors, skill=incumbent.model_dump()))
        return incumbent
