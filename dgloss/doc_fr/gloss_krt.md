# Track Gloss — spécification de référence

## Finalité

Track Gloss est un traitement final d'un routage existant. Il cherche une
géométrie plus courte sans effectuer d'autoroutage et sans modifier le dessin
autrement que par ce traitement final.

L'ordre impératif des objectifs est :

1. respecter les données d'entrée et toutes les règles applicables ;
2. réduire la longueur totale du cuivre ;
3. à longueur équivalente, réduire le nombre de segments ;
4. conserver une sortie exclusivement octolinéaire : 0°, 45° ou 90° ;
5. ne produire ni micro-segment, ni décrochement, ni détour inutile.

## Portée

- Le gloss peut traiter un seul net, plusieurs nets ou une ou plusieurs
  branches élémentaires explicitement désignées.
- Une branche élémentaire est le chemin maximal non ramifié contenant sa
  graine. Elle s'arrête à un pad, une extrémité libre ou une jonction T/X.
  Elle reste continue à travers un changement de largeur, un changement de
  couche et un via qui ne constitue pas lui-même une ramification.
- Hors portée, le reste du net est conservé et participe aux mêmes contrôles
  de topologie et d'obstacles que le cuivre des autres nets.
- Une connexion est considérée de pad fixe à pad fixe et reste continue à
  travers ses vias.
- Seul le cuivre appartenant à la connexion examinée peut être modifié ; tout
  autre cuivre demeure un obstacle.
- Un changement de largeur ne constitue pas à lui seul une terminaison ou une
  coupure de connexion.
- Aucune apparence supposée ne confère une protection implicite à une piste.

Avant toute transformation, les nets suivants sont exclus intégralement de la
portée modifiable :

1. groupes à longueur ou temps imposé ;
2. paires différentielles couplées ;
3. nets avec contrainte d'impédance ;
4. nets contenant du cuivre verrouillé, piste ou via ;
5. nets contenant des arcs.

Ces exclusions restent des obstacles pour les autres nets. Une sélection
explicite ne lève pas leur protection.

## Règles et sécurité

**MO3 — Éléments fixes et protégés.** Tout élément qualifié de fixe,
verrouillé ou protégé conserve sa position, sa géométrie et ses attributs. Il
peut servir d'ancre ou d'obstacle, mais aucune étape du gloss ne peut le
déplacer, le remplacer ou le modifier. Une mobilité n'est autorisée que
lorsqu'une règle la prévoit explicitement et que toutes ses conditions sont
satisfaites.

- Les règles effectives, les largeurs, les clearances, les obstacles, les
  keepouts, les trous, les zones pertinentes et les bords de carte restent
  autoritaires.
- Toute transformation conserve la connectivité, la topologie électrique, les
  attributs imposés et l'absence de nouvelle faute DRC.
- Une transformation non entièrement certifiée n'est jamais appliquée.
- Un échec propre au gloss restitue sans perte le routage reçu en entrée.

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
