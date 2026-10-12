# Gloss

## 1. Raccourcir et simplifier

Une piste routée est une suite de segments reliant des points fixes, tels que
des pads, des vias immobiles ou des jonctions. Elle doit rester connectée et
respecter les distances minimales au cuivre voisin.

Le **Gloss** améliore cette géométrie :

| Action | But | Effet possible sur la longueur |
|---|---|---|
| Gloss | Raccourcir et simplifier le chemin | La réduit, ou la conserve en supprimant un détour inutile |

Le Gloss ne redessine pas librement une connexion. Il travaille sur le cuivre
déjà routé, seulement là où une modification est autorisée.

## 2. Règles communes

Les éléments fixes et les zones protégées sont d'abord identifiés. Ils servent
d'ancres ou d'obstacles et ne sont jamais déplacés. Chaque modification doit
préserver les propriétés suivantes :

- la connexion électrique reste continue ;
- les largeurs, les couches et les attributs imposés restent inchangés ;
- les distances requises aux autres éléments sont respectées ;
- aucune piste ne traverse un obstacle ;
- aucun segment minuscule, décrochement gratuit ou détour inutile n'est créé ;
- la géométrie conserve les directions autorisées par le routage de la carte.

La portion modifiée est limitée à une portée autorisée. Le reste du net ne
bouge pas et reste pris en compte comme obstacle lorsque c'est nécessaire.

### Le corridor admissible

Le corridor admissible est l'ensemble des positions qu'un élément peut atteindre
depuis sa position initiale par un mouvement continu et sûr. Le départ et
l'arrivée ne suffisent donc pas : tout le déplacement entre les deux doit aussi
être valide.

Une piste ne peut pas, par exemple, passer de l'autre côté d'un obstacle parce
que sa seule position finale serait libre. La même règle s'applique aux vias et
aux jonctions lorsqu'ils sont mobiles.

#### Illustration — Mouvement continu autour des obstacles

![Un trajet continu sûr contourne les obstacles, contrairement au trajet direct barré.](../../docs/assets/admissible-corridor.png)

## 3. Le Gloss

### 3.1 Son but

Le Gloss rend un routage existant plus direct. Il cherche d'abord les portions
qui peuvent être raccourcies, puis les formes de même longueur utilisant moins
de segments. S'il n'existe aucune amélioration sûre, la piste est conservée.

![Un détour est remplacé par une liaison directe.](../../docs/assets/gloss-before-after.png)

### 3.2 Le principe géométrique

Le Gloss raisonne sur les relations entre segments voisins, jamais sur leur nom
ni leur orientation à l'écran. Un segment intérieur peut être déplacé
parallèlement à lui-même. Ses extrémités sont alors recalculées pour rejoindre
les segments qui l'encadrent.

Le même raisonnement vaut quelle que soit l'orientation des segments. Tourner
ou refléter la même forme ne doit pas lui donner un traitement différent. Les
limites du mouvement viennent des ancres, des segments voisins, des obstacles
et des règles communes.

### 3.3 Choisir une amélioration

Pour chaque mouvement possible, le Gloss reconstruit la portion concernée et
vérifie qu'elle est réalisable. Parmi les candidats valides, il privilégie :

1. une réduction de longueur utile ;
2. à longueur équivalente, une réduction du nombre de segments ;
3. à résultat équivalent, la géométrie la plus simple.

Un gain trop petit pour être distingué de la résolution de la grille n'est pas
retenu. Cela évite les changements invisibles, instables ou créant de très
petits segments.

#### Illustration — Même connexion, moins de segments

![Une piste en zigzag est remplacée par une piste plus simple aux mêmes extrémités.](../../docs/assets/segment-count-reduction.png)

### 3.4 Ce que le Gloss peut améliorer

Le Gloss peut notamment enlever un détour entre des segments voisins, fusionner
des segments alignés, raccourcir une arrivée de piste ou déplacer localement un
via ou une jonction lorsque leur mobilité est explicitement autorisée. Chaque
amélioration reste locale : elle ne donne pas le droit de déplacer un élément
fixe, de modifier une zone protégée ou de changer la fonction électrique d'une
connexion.

#### Illustration — Déplacer un via pour raccourcir ses deux jambes

![Un via déplacé sur une position plus directe réduit les deux portions de piste qui y aboutissent.](../../docs/assets/mobile-via-reduces-length.png)

## 4. Résultat attendu

Le résultat peut être une piste plus courte, une piste plus simple, ou la piste initiale si aucune amélioration ne
respecte toutes les règles. L'absence de modification est normale : elle
signifie que la géométrie existante est déjà la meilleure solution sûre dans la
portée examinée.
