"""Read-only environment checks. Never starts Kit unless --sim is explicit."""
import importlib.util
import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path

ARENA_SHA = 'c7edf3a9d5d8276565208f72422f8f8a0806d6cf'
LAB_SHA = '91a0906f93802eb859192dcb0bca879f891e92d6'


def capture(args, timeout=15):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return dict(ok=r.returncode == 0, code=r.returncode, stdout=r.stdout.strip(), stderr=r.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(ok=False, error=type(exc).__name__)


def doctor(root):
    root = Path(root)
    arena = root/'third_party/IsaacLab-Arena'
    arena_check = capture(['git', '-C', str(arena), 'rev-parse', 'HEAD'])
    lab_check = capture(['git', '-C', str(arena/'submodules/IsaacLab'), 'rev-parse', 'HEAD'])
    checks = dict(python=dict(version=platform.python_version(), executable=sys.executable,
                             ok=sys.version_info[:2] == (3,12)),
        platform=dict(system=platform.system(), machine=platform.machine(),
                      ok=platform.system()=='Linux' and platform.machine()=='x86_64'),
        arena=dict(**arena_check, matches_lock=arena_check.get('stdout')==ARENA_SHA),
        isaac_lab=dict(**lab_check, matches_lock=lab_check.get('stdout')==LAB_SHA),
        gpu=capture(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used', '--format=csv']),
        docker=capture(['docker', 'version', '--format', '{{.Server.Version}}']),
        image=capture(['docker', 'image', 'inspect', 'nvcr.io/nvidia/isaac-sim@sha256:0c16dd67d09a70ea474f2c809a13c4d09bd23c738184cf1bf28af487ecd39080', '--format', '{{json .RepoDigests}}']),
        arena_import=dict(ok=importlib.util.find_spec('isaaclab_arena') is not None))
    expected = {'isaacsim': '6.1.0.0', 'isaaclab': '17.0.2', 'isaaclab-arena': '0.3.0', 'torch': '2.11.0+cu128'}
    versions = {}
    for package in expected:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    spec = importlib.util.find_spec('isaaclab_arena')
    expected_origin = arena/'isaaclab_arena/__init__.py'
    own_arena = spec is not None and Path(spec.origin).resolve() == expected_origin.resolve()
    checks['runtime_packages'] = dict(actual=versions, expected=expected, ok=versions == expected)
    checks['arena_import'].update(origin=spec.origin if spec else None, own_checkout=own_arena)
    ready = (checks['python']['ok'] and checks['platform']['ok']
        and checks['arena']['matches_lock'] and checks['isaac_lab']['matches_lock']
        and checks['gpu']['ok'] and checks['arena_import']['ok']
        and own_arena and checks['runtime_packages']['ok'])
    return dict(status='READY_FOR_SIM_PROBE' if ready else 'BLOCKED_ENVIRONMENT',
        gpu_verified=False, formal_result_eligible=False, checks=checks)
