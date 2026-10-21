from .hashing import digest


def adaptation_identity(skill, *, run_seed_id, embodiment, controller_hash,
                        adapter_hash, proposer_config, public_context, rng_seed,
                        budget, train_conditions_hash, validation_conditions_hash):
    return digest(dict(skill=skill.model_dump(), run_seed_id=run_seed_id,
        embodiment=embodiment, controller_hash=controller_hash, adapter_hash=adapter_hash,
        proposer_config=proposer_config, public_context=public_context, rng_seed=rng_seed,
        budget=budget, train=train_conditions_hash, validation=validation_conditions_hash))
