"""Regenerate vector PDF figures from the checked CSVs; no model calls."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import argparse
import json

FIG = None
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "pdf.fonttype": 42, "ps.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False})

def save(fig, stem):
    fig.savefig(FIG / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{stem}.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

def rows(stem):
    with (FIG / f"{stem}.csv").open(newline="") as f:
        return list(csv.DictReader(f))

def effects():
    data = rows("maintenance_intervention_effects")
    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    labels=[]
    for i,r in enumerate(data):
        mean,lo,hi=(float(r[k]) for k in ("mean","ci_low","ci_high"))
        y=len(data)-1-i
        color="#214f73" if i<2 else "#247368"
        ax.errorbar(mean,y,xerr=[[mean-lo],[hi-mean]],fmt="o",capsize=4,
                    color=color,markersize=6,linewidth=1.7)
        labels.append(r["model"]+"\n"+("Analyser feedback" if r["contrast"]=="H3" else "Design guidance"))
    ax.axvline(0,color="#777777",lw=.9,linestyle="--")
    ax.set_yticks(list(reversed(range(len(data)))),labels)
    ax.tick_params(axis="y",length=0,pad=9)
    ax.set(xlim=(-.1,1.92),ylim=(-.6,3.6),xlabel="Mean reduction in newly present findings per target")
    ax.grid(axis="x",alpha=.15)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    save(fig,"maintenance_intervention_effects")

def equivalence():
    data=rows("starting_state_equivalence")
    fig,ax=plt.subplots(figsize=(7.1,3.4))
    ax.axvspan(-1,1,color="#eef2f5",label="Implemented margin: ±1")
    ax.axvspan(-.5,.5,color="#dcebe5",label="Later protocol reading: ±0.5")
    for bound in [-.5,.5]: ax.axvline(bound,color="#458071",ls="--",lw=.9)
    labels=[]
    for i,r in enumerate(data):
        m,lo,hi=(float(r[k]) for k in ("mean","ci_low","ci_high"))
        ax.errorbar(m,2-i,xerr=[[m-lo],[hi-m]],fmt="o",capsize=4,color="#214f73",lw=1.7)
        labels.append(r["study"])
    ax.axvline(0,color="#777777",lw=.7)
    ax.set_yticks([2,1,0],labels)
    ax.tick_params(axis="y",length=0,pad=8)
    ax.set(xlim=(-1.12,1.12),ylim=(-.65,2.6),xlabel="Newly present findings: repaired minus original")
    ax.annotate("Opus lower bound: −0.501678",xy=(-.501678,0),xytext=(-1.04,-.47),
                fontsize=8.3,arrowprops={"arrowstyle":"-", "lw":.7})
    ax.legend(loc="upper center",bbox_to_anchor=(.5,1.22),ncol=2,frameon=False,fontsize=8.3)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    save(fig,"starting_state_equivalence")

def main():
    global FIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent / 'data/maintenance_aggregates.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    FIG = args.out
    FIG.mkdir(parents=True, exist_ok=True)
    results = json.loads(args.data.read_text(encoding='utf-8'))['results']
    effect_rows = []
    for key, model in [('gpt', 'gpt-5.6-sol'), ('opus', 'Claude Opus 5.5')]:
        for contrast in ('H3', 'H4'):
            r = results[key]['confirmatory'][contrast]
            effect_rows.append([model, contrast, r['mean'], *r['ci95'], .95])
    with (FIG / 'maintenance_intervention_effects.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['model', 'contrast', 'mean', 'ci_low', 'ci_high', 'confidence'])
        writer.writerows(effect_rows)
    comparisons = [('v0.3 corpus', results['corpus_introductions']['R_minus_O_new_findings']),
                   ('v0.4 gpt-5.6-sol', results['gpt']['secondary']['replication']['N_RN_minus_ON']),
                   ('v0.6 Opus', results['opus']['secondary']['replication']['N_RN_minus_ON'])]
    with (FIG / 'starting_state_equivalence.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['study', 'mean', 'ci_low', 'ci_high', 'confidence', 'implemented_margin'])
        writer.writerows([name, r['mean'], *r['ci90'], .90, r['sesoi']] for name, r in comparisons)
    effects()
    equivalence()


if __name__ == '__main__':
    main()
