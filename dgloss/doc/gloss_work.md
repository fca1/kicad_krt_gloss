# Track Gloss — synthèse de travail exécutable

Ce document traduit la spécification fonctionnelle
[`gloss_krt.md`](gloss_krt.md) en architecture, étapes et responsabilités
techniques. `gloss_krt.md` reste l'autorité : en cas d'écart, ce document doit
être corrigé et non la spécification assouplie.

## Principes d'implémentation

- Considérer KRT comme une bibliothèque et écrire le moins de code possible.
- Le routage reçu, les règles KiCad et les contrôles KRT sont l'autorité de
  l'adaptation actuelle de la spécification générique.
- Ne modifier ni Rust, ni les algorithmes KRT, ni le remplissage amont de la
  grille sans accord explicite.
- Employer les types, la géométrie, le calcul de longueur, la connectivité, les
  règles et les contrôles d'obstacles déjà validés par KRT.
- Travailler à la résolution réelle de la grille KRT. Aucune recherche
  arbitraire au micron et aucune résolution indépendante ne sont introduites.
- Accepter uniquement un gain strictement supérieur au pas de grille utile.

## Liaison post-smooth

Deux entrées sont séparées :

1. `run_final_gloss()` est l'adaptateur du plugin. Il demande le dernier
   `smooth_octolinear_chains()` à KRT, puis transmet ce résultat au gloss.
2. `run_post_smooth_gloss()` reçoit un résultat déjà smoothé. Cette entrée ne
   relance jamais le smooth. Elle reste une API Python publique compatible KRT,
   afin que KRT puisse appeler dgloss à la fin de son dernier smooth ou
   l'intégrer ultérieurement plus étroitement à son processus d'autoroutage.

Le contrat détaillé de cette seconde entrée est défini dans
[`gloss_krt_python_api.md`](gloss_krt_python_api.md). Son maintien ne dépend pas
de la création d'un CLI.

Le gloss n'est appelé qu'une fois, après tous les smooth intermédiaires et la
réconciliation finale. `build_gloss_context()` reconstruit alors, depuis le
cuivre final, les couches, caches, obstacles et grilles nécessaires avec les
constructeurs KRT. `KrtClearanceAdapter` reste une couche d'adaptation mince
vers les contrôles KRT ; il ne recrée pas un moteur de clearance parallèle.

## Décomposition des étapes

### G0 — intégration transparente

Brancher le gloss après le dernier smooth, reconstruire son contexte depuis le
résultat final et rendre une sortie identique lorsque le gloss ne transforme
rien. Aucun traitement spécifique à l'absence de sélection de nets n'est
introduit.

### G1 — visualisation

Afficher uniquement les changements : ancien cuivre en pointillés, nouveau
cuivre en trait continu, anciennes et nouvelles positions des vias mobiles.
La visualisation est aval du calcul et ne peut ni permettre, ni interdire une
transformation. Elle appartient exclusivement à l'adaptateur du plugin : le
cœur `dgloss` ne connaît ni `pcbnew`, ni les couches User. `add_layer_user()`
active et nomme une couche User libre sans écraser une couche occupée.

### G2 — essai d'intégration supprimé

L'élargissement provisoire des pistes a uniquement servi à vérifier les
échanges de données, les obstacles et le retour vers KiCad. Son algorithme et
toute reconstruction particulière de clearance ont été supprimés ; ils ne
doivent pas servir de base au gloss.

### G3 — réduction des chaînes ordinaires

Réduire la longueur net par net, vias fixes, en parcourant les chaînes simples.
Les raccordements d'une diagonale peuvent glisser sur les segments adjacents,
au pas de la grille KRT. Chaque candidat est comparé à la chaîne existante,
contrôlé par KRT puis soumis au contrôle de connectivité avant application.

### G3.1 — vias mobiles locaux

Autoriser les vias satisfaisant les quatre conditions de mobilité et optimiser
leurs deux jambes incidentes sans modifier leurs attributs.

### G3.2 — terminaisons de pads

Optimiser la chaîne terminale jusqu'au point natif fixe du pad. Les contrôles
KRT gèrent directement le statut du pad du même net ; aucun découpage manuel de
la grille autour du pad n'est ajouté.

### G3.3 — T glissants et nœuds

Identifier un rail colinéaire, conserver ce rail et rechercher le meilleur
raccord de branche sur ses positions de grille. Le raccord peut être à 90° sur
le rail. L'option `enable_noncollinear_t_rails`, active par défaut, essaie aussi
chacun des trois segments d'un T sans rail colinéaire comme branche mobile et
nettoie atomiquement le coude parasite éventuellement laissé à l'ancien nœud.

### G3.4 — vias et chaînes complètes

Réemployer le moteur G3.1, en étendant l'évaluation aux deux portions complètes
articulées par le via mobile.

### G3.5 — coordination complète

Exécuter G3 puis les étapes G3.1 à G3.4 autorisées par la configuration sous un
budget global. G3.5 termine ensuite l'objectif lexicographique sur le nombre de
segments : le moteur G3 est rappelé en mode « longueur égale, moins de
segments », avec les seuls raccords canoniques KRT, puis
`merge_collinear_segments()` de KRT fusionne les alignements stricts sans
déplacer le cuivre.

Une certification finale commune vérifie : longueur non croissante,
connectivité de tous les nets, géométrie octolinéaire et aucun segment créé par
une transformation géométrique plus court que le pas réel de la grille. Une
réémission géométriquement conservatrice de KRT n'est pas assimilée à une
création de cuivre. À l'échec, restaurer exactement le résultat KRT.

G3.5 agrège une instance `GlossStats`, conserve le gain du smooth KRT séparé du
gain dgloss et produit une vue cumulée de debug sans dupliquer le cuivre.

### G4 — passes de convergence

Lorsque `enable_multipasses` est actif, G4 rappelle la chaîne G3.5 complète
pour chaque net. Une liste vide signifie tous les nets. L'ordre déterministe
alterne entre croissant et décroissant à chaque passe ; le résultat accepté
d'un net est immédiatement utilisé pour construire le contexte du suivant.
Les passes s'arrêtent à la première passe complète sans transformation ou à
l'expiration du budget global. G4 ne possède aucun algorithme géométrique
propre : il orchestre exclusivement G3.5 et ses options.

G4 appelle directement le noyau interne `_run_g3_5_pass()` avec `[net_id]`.
Il ne rappelle jamais l'entrée publique G0. Le noyau reconstruit néanmoins le
contexte KRT depuis le cuivre courant pour chaque net. Une erreur remonte sans
être convertie en résultat vide ; G0 restaure alors atomiquement tout le gloss.

À partir de G4, seule User.1 présente l'écart entre l'entrée du gloss et son
résultat final.

### G5 — certification de conformité

G5 ne génère aucune géométrie. Après G4, il réutilise le graphe de connectivité
KRT pour vérifier que la partition des pads et des zones de chaque net est
strictement inchangée. Il revalide ensuite, avec l'adaptateur de règles KRT,
chaque segment final effectivement déplacé et chaque via final mobile.

Les dimensions, couches, net, verrouillage et attributs de fabrication d'un via
mobile sont comparés avant/après. Les segments seulement réémis par la fusion
colinéaire KRT sont identifiés comme géométriquement conservés et ne sont pas
confondus avec du cuivre déplacé. Toute non-conformité déclenche le repli
atomique déjà possédé par G0.

## Modules et responsabilités

| Module | Responsabilité |
|---|---|
| `pipeline.py` | Entrée G0, noyau G3.5, certification G5 et repli |
| `context.py` | Reconstruction du contexte de grille KRT |
| `krt_clearance.py` | Adaptation mince aux contrôles KRT |
| `algorithm.py` | G3, chaînes ordinaires |
| `via_mobile.py` | G3.1 et G3.4 |
| `pad_terminals.py` | G3.2 |
| `sliding_nodes.py` | G3.3 |
| `config.py` | Options appartenant à dgloss |
| `stats.py` | Statistiques structurées et lignes de log |
| `passes.py` | G4, répétition multinet déterministe de G3.5 |
| `gloss.py` | CLI autonome, sélection et sortie compatibles KRT |
| `kicad_krt_gloss/board_adapter.py` | Adaptateur `pcbnew` entre le PCB vivant et les types KRT |
| `kicad_krt_gloss/gloss_visualization.py` | Couche User.1 et rendu final avant/après |

## Validation et traçabilité

Chaque étape donne lieu à une sortie testable, puis à un commit et un tag du
même nom. Les rapports historiques G3 à G3.5 restent dans `dgloss/`. Les tests
ciblés vérifient les transformations, les invariants, la désactivation des
options, le budget et l'absence de second smooth dans l'entrée post-smooth.
