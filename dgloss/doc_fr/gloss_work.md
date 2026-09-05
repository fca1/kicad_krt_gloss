# Track Gloss — synthèse de travail exécutable

Ce document traduit la spécification fonctionnelle
[`gloss_rules.md`](gloss_rules.md) en architecture, étapes et responsabilités
techniques. `gloss_rules.md` reste l'autorité : en cas d'écart, ce document doit
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
- Pour les phases de réduction, accepter uniquement un gain strictement
  supérieur au pas de grille utile ; le centering est évalué après selon son
  objectif propre.

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
réconciliation finale. G0 résout alors une fois la sélection et les exclusions,
puis `build_gloss_context()` reconstruit, depuis le cuivre final, les couches,
caches, obstacles et grilles nécessaires avec les constructeurs KRT. Les nets
protégés par KRT et les nets à arcs sont retirés de la portée modifiable avant
cette construction ; ils restent présents comme obstacles. Un via verrouillé
protège son net complet, conformément à la politique KRT.

Le même `GlossContext` est transmis à toute la chaîne et à G4. Les mises à jour
ultérieures remplacent seulement le cache KRT du net effectivement modifié ;
elles ne reconstruisent ni la grille, ni la base d'obstacles. Les modules issus
des jalons G3.x fournissent uniquement leurs recherches géométriques internes :
ils ne résolvent plus leur propre sélection et ne recalculent plus de liste de
nets verrouillés. `KrtClearanceAdapter` reste une couche d'adaptation mince vers
les contrôles KRT ; il ne recrée pas un moteur de clearance parallèle.

### Portée par branche élémentaire

Lorsqu'un appelant fournit des segments graines, G0 construit une seule fois
leur union de branches élémentaires depuis la topologie KRT finale. Le parcours
s'arrête aux pads, extrémités libres et jonctions ; il emploie les primitives
KRT de géométrie des pads et de portée des vias. Le net complet reste présent
pour les obstacles et les contrôles de connectivité.

Le contexte transporte l'ensemble des identités de segments modifiables. À
chaque remplacement accepté, il retire les anciennes identités et ajoute les
nouvelles. Les étapes G3 à G3.5 filtrent sur cet ensemble commun au lieu de
reconstruire la branche. Le dernier smooth et la fusion collinéaire restent les
fonctions KRT : un résultat temporaire limité à la branche active leur option
`keep_input_copper`, puis l'adaptateur réconcilie leurs ajouts et suppressions
avec le résultat réel. Aucun changement de KRT ou de Rust n'est nécessaire.

Dans un T à rail collinéaire, la branche sélectionnée peut déplacer son point
de raccordement sur le rail car le cuivre du rail demeure géométriquement
inchangé. La variante sans rail collinéaire n'est tentée que si toutes les
branches qu'elle devrait réécrire appartiennent à la portée modifiable.

La vue d'obstacles étrangers est également unique pour toute l'exécution. Elle
est clonée une seule fois depuis la grille KRT persistante, puis l'exclusion
passe d'un net au suivant avec les opérations batch d'ajout et de retrait déjà
fournies par KRT. Lorsqu'un net change, son cache recalculé remplace l'ancien
dans la grille persistante et dans cette vue réutilisable. Cette organisation
évite une copie profonde de la grille pour chaque couple étape/net sans changer
son contenu observable ni les règles de clearance.

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
au pas de la grille KRT. La recherche part de la géométrie existante par bonds
de cinq cellules KRT. Au premier obstacle confirmé par le contrôle exact KRT,
elle revient dans le dernier intervalle et l'affine cellule par cellule. La
famille est abandonnée si son premier bond est réellement bloqué. Le candidat
retenu est comparé à la chaîne existante, contrôlé par KRT puis soumis au
contrôle de connectivité avant application.

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
articulées par le via mobile. La grille Rust KRT sert d'abord de filtre de rejet
strict pour écarter rapidement les raccords manifestement bloqués. Les raccords
qui franchissent ce filtre restent soumis au contrôle géométrique exact KRT :
le filtre ne constitue jamais une validation suffisante.

### G3.5 — coordination complète

Exécuter G3 puis les étapes G3.1 à G3.4 autorisées par la configuration sous un
budget global. G3.5 termine ensuite l'objectif lexicographique sur le nombre de
segments : le moteur G3 est rappelé en mode « longueur égale, moins de
segments », avec les seuls raccords canoniques KRT, puis
`merge_collinear_segments()` de KRT fusionne les alignements stricts sans
déplacer le cuivre.

Une certification finale commune vérifie la connectivité de tous les nets, la
géométrie octolinéaire et l'absence de segment créé par une transformation
géométrique plus court que le pas réel de la grille. Les phases de réduction
respectent le gain strictement supérieur au pas utile de la grille ; le
centering, exécuté ensuite, est évalué selon son objectif de passage entre les
obstacles et peut conserver ou augmenter légèrement la longueur. Une
réémission géométriquement conservatrice de KRT n'est pas assimilée à une
création de cuivre. À l'échec, restaurer exactement le résultat KRT.

G3.5 agrège une instance `GlossStats`, conserve le gain du smooth KRT séparé du
gain dgloss et produit une vue cumulée de debug sans dupliquer le cuivre.

### G4 — passes de convergence

Lorsque `enable_multipasses` est actif, G4 rappelle la chaîne G3.5 complète une
fois par passe avec toute la liste de nets. Une liste vide signifie tous les
nets. L'ordre déterministe alterne entre croissant et décroissant à chaque
passe ; le résultat accepté d'un net est immédiatement visible par le suivant.
Les passes s'arrêtent à la première passe complète sans transformation ou à
l'expiration du budget global. G4 ne possède aucun algorithme géométrique
propre : il orchestre exclusivement G3.5 et ses options.

G4 appelle directement le noyau interne `_run_g3_5_pass()` une seule fois par
passe, avec la liste complète dans l'ordre retenu et le `GlossContext` unique
préparé par G0. Il ne rappelle ni l'entrée publique G0, ni
`build_gloss_context()`. Après une transformation, seul le cache d'obstacles du
net concerné est remplacé. Une erreur remonte sans être convertie en résultat
vide ; G0 restaure alors atomiquement tout le gloss.

À partir de G4, une seule couche User présente l'écart entre l'entrée du gloss
et son résultat final.

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
| `branches.py` | Résolution unique des branches élémentaires depuis leurs graines |
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
| `kicad_krt_gloss/gloss_visualization.py` | Couche User libre et rendu final avant/après |

## Validation et traçabilité

Chaque étape donne lieu à une sortie testable, puis à un commit et un tag du
même nom. Les rapports historiques sont classés dans `docs/reports/`. Les
tests ciblés vérifient les transformations, les invariants, la désactivation
des options, le budget et l'absence de second smooth dans l'entrée post-smooth.
