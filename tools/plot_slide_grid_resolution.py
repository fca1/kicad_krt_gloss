"""Plot single-pass shadow timings; requires matplotlib only for rendering."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    fig, axes = plt.subplots(2, len(args.inputs), figsize=(12, 7.5), squeeze=False)
    steps = ['0.1', '0.05', '0.025']
    for column, path in enumerate(args.inputs):
        data = json.loads(path.read_text(encoding='utf-8'))
        rows = [data['rows'][step+'/guard'] for step in steps]
        costs = [data['costs'][step] for step in steps]
        query = [r['seconds']*1000 for r in rows]
        avoided = [r['exact_seconds_on_agreeing_free']*1000 for r in rows]
        ax = axes[0, column]
        ax.plot(steps, query, 'o-', color='#c25128', label='Coût des consultations grille')
        ax.plot(steps, avoided, 'o-', color='#267868', label='Validation potentiellement évitable')
        for series, color in ((query, '#c25128'), (avoided, '#267868')):
            for i, value in enumerate(series):
                ax.annotate(f'{value:.1f}', (i, value), xytext=(0, 7),
                            textcoords='offset points', ha='center', color=color)
        ax.set_title(Path(data['board']).stem + f" — {data['queries']:,} enveloppes".replace(',', ' '))
        ax.set_ylabel('Temps cumulé (ms)')
        ax.set_ylim(0, max(query+avoided)*1.28)
        ax.legend(fontsize=8, loc='upper left')
        ax = axes[1, column]
        build = [c['build_seconds'] for c in costs]
        update = [c['update_seconds'] for c in costs]
        select = [c['selection_seconds'] for c in costs]
        ax.bar(steps, build, label='Construction du contexte grille', color='#b3c9e4')
        ax.bar(steps, update, bottom=build, label='Mises à jour des nets', color='#537ca9')
        ax.bar(steps, select, bottom=[b+u for b,u in zip(build,update)],
               label='Sélection de la carte sans le net', color='#233f64')
        for i, (b,u,s) in enumerate(zip(build, update, select)):
            ax.text(i, b+u+s, f'{b+u+s:.2f} s', ha='center', va='bottom')
        ax.set_ylim(0, max(b+u+s for b,u,s in zip(build,update,select))*1.25)
        ax.set_ylabel('Gestion de la grille (s)')
        ax.legend(fontsize=8, loc='upper left')
        for ax in axes[:, column]:
            ax.set_xlabel('Pas de grille (mm) — finesse croissante →')
            ax.grid(axis='y', alpha=.2)
            ax.set_axisbelow(True)
    fig.suptitle('Glissement : une grille plus fine récupère-t-elle son coût ?', fontsize=16)
    fig.text(.5, .018, 'Enveloppe centrée avec garde d’arrondi • mêmes candidats • un passage par carte\n'
             'Économie hypothétique : aucun remplacement du validateur géométrique n’est autorisé par cet essai.',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0,.075,1,.95))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
