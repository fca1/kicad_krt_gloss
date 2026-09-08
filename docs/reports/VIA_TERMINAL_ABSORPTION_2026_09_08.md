# Arrêt des vias après absorption jusqu'au pad

Le correctif remplace l'arrêt au simple contact via/pad par un arrêt lié
à l'absorption effective d'une branche jusqu'à son ancre terminale. Le pad
doit appartenir au même net et à la couche de la branche absorbée ; son
contact est évalué par KRT avec la demi-largeur du segment terminal.
Le rayon du via ne définit plus cette terminaison.

Les arrêts sont mémorisés dans le contexte d'optimisation par net et position
pour rester effectifs entre G3.1, G3.4 et les passes suivantes du même Gloss.
Ils ne constituent pas un verrou permanent enregistré dans la carte.
Le contrôle utilise l'index spatial KRT en cache uniquement après une
absorption acceptée. Les validations de mouvement et de connectivité restent
inchangées ; KRT n'est pas modifié.

## Validation ciblée

59 tests réussis : progressive_via, auto_gloss, plugin_boundaries, corridor,
centering_transaction, g4_passes. Les cas ajoutés couvrent le contact initial,
le contact par le seul rayon du via, la couche du pad et la persistance de
l'arrêt après absorption dans les étapes suivantes.

Comparaison unique par configuration sur trois nets de PACK0/tildagon_base,
avec convergence locale et G4 désactivé :

| Net | Prototype précédent, gain mm | Correctif, gain mm | Temps étapes précédent, ms | Temps étapes correctif, ms |
| --- | ---: | ---: | ---: | ---: |
| 112 | 0.165713 | 1.168405 | 376.52 | 370.50 |
| 150 | 12.464038 | 12.464038 | 5193.50 | 5346.43 |
| 170 | 1.450355 | 1.874619 | 618.95 | 636.87 |

Les six exécutions passent G5. Les temps sont la somme des étapes mesurées,
hors chargement et certification finale ; ce ne sont pas des mesures
statistiques permettant de conclure sur un petit écart de performances.
Le net 150 conserve volontairement son arrêt au pad terminal.

Commande : `python tools/diagnose_via_losses.py --nets 112 150 170 --modes production prototype --output .build/terminal_absorption_validation.json`.
Le mode production désigne ici le code corrigé ; prototype désigne la copie
historique dans tools/progressive_via.py, laissée inchangée.
