"""Publication-friendly plots from all observed independent learning-run points."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(suite):
    report=json.loads((suite/'report.json').read_text())
    groups=report['groups']
    if not groups:
        return {'status':'NO_COMPLETED_LEARNING_RUNS','plots':[]}
    with (suite/'run_points.csv').open('w',newline='') as stream:
        fields=['learner','source','target','budget','run_seed_id','delta_new','before_success_rate','after_success_rate',
                'source_accepted_update','adaptation_aliased']
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
        writer.writeheader()
        for group in groups:
            for point in group['points']:
                writer.writerow({**{k:group[k] for k in fields[:4]},**point})
    learners=sorted({g['learner'] for g in groups})
    directions=sorted({(g['source'],g['target']) for g in groups})
    figure,axes=plt.subplots(len(directions),len(learners),figsize=(6*len(learners),3.8*len(directions)),squeeze=False)
    for row,direction in enumerate(directions):
        for column,learner in enumerate(learners):
            axis=axes[row,column]
            cells=sorted([g for g in groups if g['learner']==learner and (g['source'],g['target'])==direction],key=lambda g:g['budget'])
            if not cells:
                axis.set_visible(False)
                continue
            seeds=sorted({p['run_seed_id'] for g in cells for p in g['points']})
            for seed in seeds:
                points=[(g['budget'],p['delta_new']) for g in cells for p in g['points'] if p['run_seed_id']==seed]
                axis.plot([p[0] for p in points],[p[1] for p in points],marker='o',alpha=.45,linewidth=1,label=f'run {seed}')
            budgets=[g['budget'] for g in cells]
            axis.plot(budgets,[g['mean_delta'] for g in cells],color='black',linewidth=2,marker='s',label='mean')
            axis.fill_between(budgets,[g['minimum_delta'] for g in cells],[g['maximum_delta'] for g in cells],color='grey',alpha=.12,label='min–max')
            axis.axhline(0,color='grey',linewidth=.8,linestyle='--')
            axis.set(title=f'{learner}\n{direction[0]} → {direction[1]}',xlabel='Fresh target adaptation budget',
                     ylabel='Success-rate difference: After − Before',xticks=budgets)
            axis.set_ylim(min(-.05,min(g['minimum_delta'] for g in cells)-.05),max(.05,max(g['maximum_delta'] for g in cells)+.05))
            axis.grid(alpha=.2)
            axis.legend(fontsize=8)
    track='Frozen internal pilot' if report['formal_result_eligible'] else 'Development / unaudited results'
    figure.suptitle(track+' — all independent learning-run points')
    figure.text(.5,.01,'Shading is the observed run range, not a confidence interval. Lines only join measured budgets.',ha='center',fontsize=9)
    figure.tight_layout(rect=(0,.035,1,.95))
    for extension in ('svg','pdf'):
        figure.savefig(suite/f'budget_response.{extension}')
    plt.close(figure)
    return dict(status='PLOTS_GENERATED',plots=['budget_response.svg','budget_response.pdf'],data='run_points.csv')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--suite',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(plot(a.suite)))
