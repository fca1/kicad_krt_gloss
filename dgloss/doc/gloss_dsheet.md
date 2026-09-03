# Track Gloss — fiche d'emploi

Cette fiche décrit comment employer et observer Track Gloss. Le besoin est
défini dans [`gloss_krt.md`](gloss_krt.md) et sa réalisation dans
[`gloss_work.md`](gloss_work.md).

## État du composant

- Branche de développement : `main`
- Version du plugin : `0.1.0`
- Étape intégrée : G5
- Portée : nets complets sélectionnés ; sans sélection, tous les nets routés
- Déclenchement : une fois, après le dernier smooth KRT
- Budget plugin par défaut : 20 secondes
- CLI dédié : `gloss.py`

## Emploi en ligne de commande

Le CLI reprend les conventions KRT : noms et motifs de nets, `--nets`,
`--component`, `--group`, `--group-by`, `--group-scope` et `--list-groups`.
Sans sélection, tous les nets routés sont traités. Une sélection désigne
toujours des nets complets.

```text
python gloss.py input.kicad_pcb output.kicad_pcb --nets "/Cpu/*"
python gloss.py input.kicad_pcb --component U1 --preview
python gloss.py input.kicad_pcb --json-out gloss-summary.json
```

Les paramètres omis sont résolus par les modules KRT depuis la classe Default
du projet, les classes propres aux nets et les règles `.kicad_dru`. Le pas de
grille autonome reste celui de KRT, `0,1 mm`, sauf `--grid-step` explicite.
La sortie comprend un bilan lisible, `JSON_SUMMARY`, `JSON_SUMMARY_MIN` et,
avec `--json-out`, le bilan JSON complet dans un fichier.

## Emploi depuis le plugin

Le plugin autonome exécute le dernier smooth KRT puis Track Gloss. Les options
suivantes sont visibles dans sa boîte de dialogue et activées par défaut :

| Option | Effet |
|---|---|
| `Track Gloss G3.1 — mobile vias` | Autorise le déplacement local des vias mobiles |
| `Track Gloss G3.2 — pad terminals` | Autorise l'optimisation des terminaisons de pads |
| `Track Gloss G3.3 — sliding T nodes` | Autorise les branches de T glissantes |
| `Track Gloss G3.3 — allow non-collinear rails` | Autorise la variante des T sans rail colinéaire |
| `Track Gloss G3.4 — complete via chains` | Autorise l'optimisation complète autour des vias |
| `G4 — multi-net convergence passes` | Répète G3.5 par net jusqu'à convergence |
| `G5 — final compliance certification` | Certifie le résultat sans modifier sa géométrie |

G3, réduction des chaînes ordinaires, constitue le socle et reste actif. Une
option décochée ne lance pas son étape et ne crée pas sa visualisation.

## Emploi comme bibliothèque Python

Pour reproduire le comportement actuel du plugin :

```python
from dgloss import GlossConfig, run_final_gloss

options = GlossConfig(
    enable_g3_1=True,
    enable_g3_2=True,
    enable_g3_3=True,
    enable_g3_4=True,
    budget_seconds=20.0,
    enable_noncollinear_t_rails=True,
    enable_multipasses=True,
)
outcome = run_final_gloss(results, pcb_data, krt_config, options)
```

Pour un appelant qui possède déjà le résultat du dernier smooth KRT :

```python
from dgloss import run_post_smooth_gloss

outcome = run_post_smooth_gloss(
    results, pcb_data, krt_config, gloss_config=options,
    net_ids=selected_net_ids, krt_smooth_complete=True
)
```

Le second emploi est strictement post-smooth : il reconstruit le contexte mais
ne relance pas `smooth_octolinear_chains()`. Le certificat
`krt_smooth_complete=True` permet au gloss de ne pas reproduire les familles
canoniques que le dernier smooth vient de traiter. C'est aussi l'API publique
prévue pour une intégration directe par KRT. Le CLI autonome ne positionne pas
ce certificat et conserve donc ces familles.

G0 construit ce contexte une seule fois, y compris lorsque G4 est actif. Avant
sa construction, il exclut les groupes à longueur/temps imposé, les paires
différentielles couplées, les nets d'impédance, tout net contenant du cuivre
verrouillé et tout net contenant un arc. Ces nets restent des obstacles.

## Configuration

`GlossConfig` est indépendante de `GridRouteConfig`. Le plugin transmet
seulement cette configuration au point d'entrée dgloss ; KRT ne dépend pas de
ses options.

| Champ | Défaut | Signification |
|---|---:|---|
| `enable_g3_1` | `True` | Active G3.1 |
| `enable_g3_2` | `True` | Active G3.2 |
| `enable_g3_3` | `True` | Active G3.3 |
| `enable_g3_4` | `True` | Active G3.4 |
| `budget_seconds` | `20.0` | Budget global post-smooth |
| `enable_noncollinear_t_rails` | `True` | Active la variante G3.3 sans rail colinéaire |
| `enable_multipasses` | `True` | Active les passes de convergence G4 sur G3.5 |

## Résultat exploitable

`GlossOutcome` fournit :

- `input_strip_segments` et `input_strip_vias`, à supprimer de la sortie KRT ;
- `changes`, description structurée des anciens et nouveaux objets ;
- `stats`, bilan structuré destiné aux tests, rapports et au CLI.

Le bilan global contient notamment les nets parcourus et améliorés, les
longueurs avant/après, les changements de segments et de vias, le gain dgloss,
le gain KRT séparé, le temps, l'état du budget et le nombre de régressions de
connectivité. `nets_excluded`, `excluded_net_ids` et `exclusion_reasons`
décrivent les exclusions décidées par G0.

La réduction finale de segments expose aussi :

- `equal_length_segment_reduction`, pour les raccords canoniques de même
  longueur comportant moins de segments ;
- `segments_merged` et `merge_joints`, pour les alignements fusionnés par KRT ;
- `equal_length_algorithm_ms` et `merge_algorithm_ms`, pour leurs temps
  respectifs.

La certification G5 expose `g5_valid`, `g5_segments_certified`,
`g5_segments_geometry_preserved`, `g5_vias_certified` et `g5_algorithm_ms`.
Elle compare également, par le graphe KRT, la partition des pads et zones avant
et après le gloss.

Le log affiche une ligne courte par étape, puis une ligne globale de la forme :

```text
Track Gloss G3.5: 120 nets parcourus, 8 améliorés, -12.3400 mm, 8500.0 ms
```

## Visualisation KiCad

La visualisation ne participe jamais aux décisions algorithmiques. Elle est
entièrement contenue dans l'adaptateur du plugin ; `dgloss` ne dépend pas de
`pcbnew`. Elle montre le cuivre modifié : ancien tracé pointillé, nouveau tracé
continu, ancienne et nouvelle positions d'un via mobile.

| Étape | Couche de debug cumulative |
|---|---|
| G3 | User.1 — `TrackGloss G3` |
| G3.1 | User.2 — `TrackGloss G3.1` |
| G3.2 | User.3 — `TrackGloss G3.2` |
| G3.3 | User.4 — `TrackGloss G3.3` |
| G3.4 | User.5 — `TrackGloss G3.4` |
| G3.5 | User.6 — `TrackGloss G3.5` |

`add_layer_user()` augmente si nécessaire le nombre de couches User, active la
couche et la nomme. Si la couche visée contient déjà des dessins étrangers,
elle n'est ni renommée ni effacée et l'overlay correspondant est omis. Les
couches User ne sont pas des couches cuivre et ne sont pas incluses dans les
Gerbers sauf ajout volontaire à un travail de tracé par l'utilisateur.

Avec G4, seule User.1 montre l'écart entre l'entrée du gloss et le résultat
final ; les vues intermédiaires G3 à G3.5 ne sont pas produites.

Le plugin nomme cette couche `TrackGloss Changes` lorsqu'elle est libre. Si
elle est déjà occupée, seule la visualisation est omise : le traitement du
cuivre et son résultat ne sont pas conditionnés par la couche User.

## Comportement en cas d'échec

Si une étape lève une erreur ou si la certification finale échoue, toutes les
modifications dgloss de l'appel sont annulées. Le cuivre issu du dernier smooth
KRT est conservé et le plugin poursuit sa restitution vers KiCad.
