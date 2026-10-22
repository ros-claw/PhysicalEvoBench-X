"""Create an explicitly non-formal evidence inventory from retained development runs."""
import argparse
import json
from pathlib import Path
from physicalevobench_x.core.hashing import write_json,file_digest


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,default=Path('evidence/development_summary.json'))
    args=parser.parse_args()
    root=args.root
    sources={
        'nominal':'evidence/gpu/nominal_summary.json',
        'calibration_panda':'evidence/gpu/calibration_panda.json',
        'calibration_robotiq':'evidence/gpu/calibration_robotiq.json',
        'dynamics_panda':'evidence/gpu/dynamics_panda.json',
        'dynamics_robotiq':'evidence/gpu/dynamics_robotiq.json',
        'source_selection':'evidence/protocol/source_random/selection.json',
        'source_costs':'evidence/protocol/source_random/costs.json',
        'zero_transfer':'evidence/protocol/zero_transfer/summary.json',
        'five_transfer':'evidence/protocol/five_transfer/summary.json',
        'kimi_adaptation_selection':'evidence/llm/kimi_k3/physical_adaptation_selection.json',
        'kimi_adaptation_costs':'evidence/llm/kimi_k3/physical_adaptation_costs.json',
        'panda_sensitivity':'runs/sensitivity-panda-v1/sensitivity.json',
        'robotiq_sensitivity':'runs/sensitivity-robotiq-v1/sensitivity.json',
        'adversarial_judge':'runs/judge-adversarial-v1/judge_adversarial.json',
    }
    snapshot={key:dict(path=path,sha256=file_digest(root/path),data=load(root/path)) if (root/path).exists()
              else dict(path=path,status='PENDING') for key,path in sources.items()}
    for key,entry in snapshot.items():
        if entry.get('data',{}).get('backend') not in (None,'physx'):
            raise ValueError('Fake evidence rejected: '+key)
    write_json(args.output,dict(schema_version='pebx.development_inventory.v1',evidence=snapshot,
        formal_result_eligible=False,note='Development engineering evidence, not pilot statistics or a transfer research conclusion'))


if __name__=='__main__':
    main()
