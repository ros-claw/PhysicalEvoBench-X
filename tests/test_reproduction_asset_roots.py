"""Asset inventories mix absolute cache paths and repository-relative resources."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reproduction_v2',ROOT/'tools/reproduce_native_install_v2.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_assets_resolve_relative_resources_against_explicit_installation(tmp_path):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    absolute=tmp_path/'shared.usd';absolute.write_text('shared')
    for root in (old,new):(root/'relative.mdl').write_text('same pinned package resource')
    inventory=tmp_path/'inventory.json';inventory.write_text(json.dumps(dict(files={
        str(absolute):dict(sha256=module.file_digest(absolute)),
        'relative.mdl':dict(sha256=module.file_digest(old/'relative.mdl'))})))
    data=dict(asset_inventory=str(inventory))
    assert module.assets(data,old)==2
    assert module.assets(data,new)==2
    (new/'relative.mdl').write_text('changed')
    with pytest.raises(ValueError,match='differs'):module.assets(data,new)


def test_missing_relative_resource_does_not_fall_back_to_old_installation(tmp_path):
    inventory=tmp_path/'inventory.json';inventory.write_text(json.dumps(dict(files={'missing.mdl':dict(sha256='unused')})))
    with pytest.raises(FileNotFoundError):module.assets(dict(asset_inventory=str(inventory)),tmp_path/'new')
