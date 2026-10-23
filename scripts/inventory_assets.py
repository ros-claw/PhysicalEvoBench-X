"""Hash transitive USD dependencies and explicitly retain unresolved references."""
import argparse
from pathlib import Path
from pxr import UsdUtils
from physicalevobench_x.core.hashing import file_digest, write_json, digest


def inventory(roots, runtime_bundles=()):
    files, unresolved = {}, set()
    for root in roots:
        if not root.is_file():
            raise ValueError('Missing root asset: '+str(root))
        layers, assets, missing = UsdUtils.ComputeAllDependencies(str(root))
        unresolved.update(str(x) for x in missing)
        for path in [root, *(Path(l.realPath) for l in layers), *(Path(a) for a in assets)]:
            if not path.is_file():
                unresolved.add(str(path))
                continue
            files[str(path)] = dict(sha256=file_digest(path), bytes=path.stat().st_size)
    resolved_by_bundle = {}
    for bundle in runtime_bundles:
        if not bundle.is_dir():
            raise ValueError('Missing runtime shader bundle: '+str(bundle))
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                files[str(path)] = dict(sha256=file_digest(path), bytes=path.stat().st_size)
                if path.name in unresolved:
                    resolved_by_bundle.setdefault(path.name, []).append(str(path))
    unresolved -= resolved_by_bundle.keys()
    report = dict(roots=[str(p) for p in roots], files=files, unresolved=sorted(unresolved),
                  runtime_bundles=[str(p) for p in runtime_bundles], runtime_bundle_matches=resolved_by_bundle,
                  scope='USD transitive graph plus complete supplied runtime shader bundles; not a renderer resolver trace',
                  verified=not unresolved, redistribution='References and hashes only; assets remain external',
                  formal_result_eligible=False)
    report['inventory_hash'] = digest(report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', action='append', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runtime-bundle', action='append', type=Path, default=[])
    a = p.parse_args()
    write_json(a.output, inventory(a.root, a.runtime_bundle))
