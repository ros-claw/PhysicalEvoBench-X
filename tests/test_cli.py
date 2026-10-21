import subprocess
import sys
from pathlib import Path
import pytest
from physicalevobench_x.core.freeze import freeze


def test_cpu_imports_do_not_start_sim():
    code='import physicalevobench_x.cli; import sys; assert not any(m.startswith(("omni", "isaaclab", "pxr")) for m in sys.modules)'
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_freeze_rejects_unvalidated_dev_config(tmp_path):
    root=Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError,match='development validation'):
        freeze(root/'configs/experiments/smoke.yaml',root,tmp_path/'frozen.json')
    assert not (tmp_path/'frozen.json').exists()
