"""CPU protocol orchestration; runner/learner injection controls trusted execution."""
from pathlib import Path
from ..core.aliasing import adaptation_identity
from ..core.hashing import digest, write_json
from .learning import learn
from .paired import paired_evaluate


def transfer(initial, *, conditions, budgets, proposer_factory, runner_factory, seed,
             identity_context, output):
    """One independent donor/receiver seed package. No cross-run result cache.

    Identity context contains all controller/adapter/proposer versions and public
    input. Source logs/provenance are deliberately absent from target requests.
    Callers must supply separate source and target physical runner factories.
    """
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    source_runner = runner_factory('source')
    after = learn(initial,20,conditions['source_train'],conditions['source_validation'],
                  proposer_factory,seed['source_proposal'],source_runner,output/'source')
    cache, aliases, summaries = {}, [], []
    for budget in budgets:
        ntrain,nval = (0,0) if budget==0 else (1,1) if budget==5 else (2,4)
        train, val = conditions['target_train'][:ntrain],conditions['target_validation'][:nval]
        outputs = []
        for label, skill in [('before',initial),('after',after)]:
            identity = adaptation_identity(skill,run_seed_id=seed['run_seed_id'],
                rng_seed=seed['target_proposal'],budget=budget,
                train_conditions_hash=digest(train),validation_conditions_hash=digest(val),**identity_context)
            path = output/'targets'/str(budget)/label
            if identity in cache:
                final, original = cache[identity]
                path.mkdir(parents=True)
                write_json(path/'frozen_output.json',final)
                aliases.append(dict(request=str(path.relative_to(output)),alias_of=str(original.relative_to(output)),
                                    target_adaptation_identity=identity, logical_episode_requests=budget,
                                    physical_episode_executions=0, budget_charged_episodes=0))
            else:
                final=learn(skill,budget,train,val,proposer_factory,seed['target_proposal'],
                            runner_factory('target'),path)
                cache[identity]=(final,path)
                write_json(path/'frozen_output.json',final)
            outputs.append((final,identity))
        # Adaptation identity equality is sufficient; also compare final execution
        # semantics when independently adapted outputs happen to converge.
        equivalent = outputs[0][0].semantic_hash==outputs[1][0].semantic_hash
        pairs=paired_evaluate(outputs[0][0],outputs[1][0],conditions['target_test'],
            lambda side:runner_factory('target'),output/'evaluations'/str(budget),equivalent=equivalent)
        delta=sum(int(p[1].task_success)-int(p[0].task_success) for p in pairs)/len(pairs)
        summaries.append(dict(budget=budget,delta_new=delta,valid_pairs=len(pairs),
                              adaptation_aliased=outputs[0][1]==outputs[1][1],evaluation_aliased=equivalent))
    write_json(output/'aliases.json',aliases)
    write_json(output/'protocol_summary.json',dict(budgets=summaries,
        note='Protocol diagnostic; physical eligibility requires independent evidence validation'))
    return summaries
