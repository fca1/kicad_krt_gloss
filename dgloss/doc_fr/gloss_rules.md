# Track Gloss — spécification de référence

Ce document fixe les règles fonctionnelles et les invariants. Pour une
présentation accessible du fonctionnement des deux actions, voir
[`gloss_explain.md`](gloss_explain.md).

## Finalité

Track Gloss est un traitement final d'un routage existant. Il améliore sa
géométrie sans effectuer d'autoroutage et sans modifier le dessin autrement
que par ce traitement final.

L'ordre impératif des objectifs est :

1. respecter les données d'entrée et toutes les règles applicables ;
2. pendant les phases de réduction, réduire la longueur avec un gain
   strictement supérieur au pas utile de la grille ;
3. à longueur équivalente, réduire le nombre de segments ;
4. conserver une sortie exclusivement octolinéaire : 0°, 45° ou 90° ;
5. ne produire ni micro-segment, ni décrochement, ni détour inutile.

## Définition

- Une graine est un segment KRT explicitement désigné comme point de départ
  d'une transformation.
- Une branche élémentaire est le chemin maximal non ramifié contenant sa
  graine. Elle s'arrête à un pad, une extrémité libre ou une jonction T/X.
  Elle reste continue à travers un changement de largeur, un changement de
  couche et un via qui ne constitue pas lui-même une ramification.
- **MO3 — Éléments fixes et protégés.** Un élément fixe, verrouillé ou protégé
  conserve sa position, sa géométrie et ses attributs. Il peut servir d'ancre
  ou d'obstacle, mais aucune étape du gloss ne peut le déplacer, le remplacer
  ou le modifier. Une mobilité n'est autorisée que lorsqu'une règle la prévoit
  explicitement et que toutes ses conditions sont satisfaites.

### Corridor admissible

Un corridor admissible est l'ensemble des positions accessibles à un élément
électrique depuis sa géométrie initiale par une déformation continue qui
respecte, à chaque instant, les clearances, l'épaisseur du cuivre, la
connectivité, les ancres fixes et le périmètre modifiable.

**L'élément ne peut ni traverser un obstacle, ni le sauter pour passer d'un côté
à l'autre**, même si les géométries initiale et finale sont toutes deux valides.
Cette interdiction concerne tout le déplacement : une piste, un via mobile ou
une jonction mobile doivent la respecter avec leurs segments incidents.

Un contournement n'est admissible que s'il existe une déformation continue
entièrement autorisée. Vérifier uniquement la destination ne démontre donc pas
le respect du corridor. Le corridor n'est ni une bande de largeur fixe autour
de la piste, ni une région définie par la grille : ses limites proviennent des
obstacles et des contraintes applicables, dont KRT reste l'autorité.

Lorsqu'un certificat ne teste qu'une déformation particulière, son échec
signifie que cette déformation n'est pas certifiée ; il ne prouve pas qu'aucune
autre déformation admissible n'existe.

## Exclusion

Avant toute transformation, les nets suivants sont exclus intégralement de la
portée modifiable :

1. groupes à longueur ou temps imposé ;
2. paires différentielles couplées ;
3. nets avec contrainte d'impédance ;
4. nets contenant du cuivre verrouillé, piste ou via ;
5. nets contenant des arcs.

Ces exclusions restent des obstacles pour les autres nets. Une sélection
explicite ne lève pas leur protection.

## Séquencement

Le Gloss et le Centering sont deux actions distinctes, aux objectifs différents.
Le Gloss cherche à réduire et à simplifier ; le Centering cherche à placer une
piste au mieux dans un passage. Le Centering peut donc conserver ou augmenter
légèrement la longueur : il n'est pas soumis au gain minimal exigé par les
phases de réduction.

Lorsqu'un Centering est demandé, l'enchaînement est impératif et atomique :

1. exécuter le Gloss avec `stay_in_corridor=True` ;
2. exécuter le Centering sur ce résultat ;
3. ne plus transformer la géométrie après le Centering.

Le Centering est ainsi la dernière transformation géométrique de l'action. En
cas d'échec, de budget expiré ou de non-conformité de cette action combinée, le
résultat initial est restauré selon la politique transactionnelle.

Les mesures publiées pour une action Gloss couvrent toute l'action, depuis le
cuivre reçu en entrée jusqu'au cuivre final. La longueur initiale, le nombre de
nets modifiés et le gain total incluent donc le lissage KRT préliminaire. Le
rapport peut détailler séparément le gain du lissage KRT et celui des phases
suivantes, mais ce détail ne remplace jamais le total complet.

## Centering

**M01 — Porte de centering.** Un obstacle isolé ne provoque aucune
transformation. Deux obstacles forment une porte lorsqu'ils encadrent le
segment, que la droite reliant leurs limites cuivre croise ce segment, qu'au
moins l'un d'eux se trouve à une distance strictement inférieure à `Proxi` et
que leur distance cuivre est strictement inférieure à `2 × Proxi`. `Proxi`
est une distance absolue exprimée en millimètres. Elle vaut `1 mm` par défaut,
peut être choisie par l'utilisateur entre `0 mm` et `5 mm`; la valeur `0 mm`
ne sélectionne aucune porte lors de l'action de centering. La netlist présente
les nets modifiables indépendamment de la valeur de `Proxi`.

Le centering place la piste sur l'axe admissible de la porte, pondéré par les
clearances effectives. Plusieurs portes peuvent conduire à décomposer la
piste en plusieurs segments. Toute géométrie produite reste octolinéaire et
est validée contre l'ensemble des obstacles par les contrôles KRT.

L'option `build_new_segments` autorise l'augmentation du nombre de segments.
Elle est cochée par défaut dans l'interface Centering. Lorsqu'elle est
désactivée, le centering choisit le meilleur recentrage réalisable sans créer
de segment supplémentaire. L'impossibilité d'atteindre le centre exact ne
constitue pas un motif de rejet.

L'option `build_multi_door_path` autorise une même transformation à traiter
plusieurs portes successives. Elle est cochée par défaut dans l'interface
Centering et reste indépendante de `build_new_segments` : la première choisit
le nombre de portes couvertes, la seconde autorise ou interdit l'augmentation
du nombre de segments nécessaire pour les relier.

Lorsque le centering est activé, les portes compatibles de toute la branche
élémentaire sont traitées avant de considérer la longueur ou le nombre de
segments. Ces deux mesures ne constituent ni un motif de rejet ni un critère
de classement entre des solutions couvrant des ensembles de portes différents.

Pour chaque porte, le franchissement utilise l'orientation octolinéaire qui
maximise la plus faible marge aux deux obstacles. Lorsque la porte est normale
au segment et que son orientation actuelle atteint cette marge, l'orientation
du segment est conservée. Une orientation différente peut être construite si
`build_new_segments` vaut `true`; elle est ensuite raccordée aux portes
précédente et suivante par la construction multiporte.

## Portée

- Le gloss traite une ou plusieurs branches élémentaires explicitement
  désignées.
- Hors portée, le reste du net est conservé et participe aux mêmes contrôles
  de topologie et d'obstacles que le cuivre des autres nets.
- Une connexion est considérée de pad fixe à pad fixe et reste continue à
  travers ses vias.
- Seul le cuivre appartenant à la connexion examinée peut être modifié ; tout
  autre cuivre demeure un obstacle.
- Un changement de largeur ne constitue pas à lui seul une terminaison ou une
  coupure de connexion.
- Aucune apparence supposée ne confère une protection implicite à une piste.

## Points imposés et topologie

### Pads

Le point d'arrivée natif du pad, généralement son centre, est fixe. Une piste
ne choisit pas arbitrairement un autre point sur son bord. Le raccord final au
pad reste octolinéaire.

### Vias

Un via fixe est une articulation traversée par la connexion, pas une
terminaison. Un via ne peut être mobile que si les quatre conditions suivantes
sont toutes satisfaites :

1. exactement deux segments du même net lui sont incidents ;
2. ces segments appartiennent à deux couches de cuivre différentes ;
3. les deux côtés appartiennent intégralement à la portée modifiable ;
4. aucune contrainte native ne fixe sa position.

Lorsqu'un via est mobile, son diamètre, son percement, son type, son net et sa
plage de couches restent inchangés. Sa position initiale demeure une solution
de repli valide.

### T et nœuds

Dans un T constitué de deux segments colinéaires formant un rail et d'une
branche, le raccord de la branche peut se déplacer sur le rail sans déplacer
celui-ci. La branche peut être perpendiculaire au rail : cet angle de 90° est
autorisé et peut être la solution minimale. Il ne doit pas être confondu avec
un coude parasite à 90° à l'autre extrémité de la branche.

Une variante peut autoriser un T sans couple colinéaire : chacun des trois
segments est successivement considéré comme branche et les deux autres comme
rails possibles. Après déplacement, tout coude parasite à 90° laissé à
l'ancien nœud est simplifié selon les règles générales du gloss. Lorsque cette
variante est désactivée, le nœud sans couple colinéaire reste fixe. Pads et vias
fixes ont priorité sur la mobilité d'un raccord.
