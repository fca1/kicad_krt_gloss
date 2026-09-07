# Causes des pertes du prototype via mobile — 7 septembre 2026

## ZIP livré avant l'analyse

`dist/prototype-via-fc23d42/KiCadKrtGloss-0.1.3-prototype-via-fc23d42.zip`.
Archive PCM installable ; le moteur expérimental remplace `plugins/dgloss/via_mobile.py`
uniquement dans le ZIP. Le dépôt conserve sa production inchangée. KRT Python
vient du sous-module courant ; les quatre binaires sont repris du package 0.1.3
local, sans téléchargement ni modification. Le nom du package indique prototype,
sa version PCM reste 0.1.3. Le fichier PROTOTYPE_VIA.md décrit l'activation et le
retour au ZIP stable. G4 conserve son réglage utilisateur : le désactiver pour
reproduire les tests. Une empreinte SHA256 accompagne le ZIP.

Vérifications : intégrité ZIP, identité octet pour octet du moteur avec le
prototype fc23d42, import en processus Python isolé depuis les fichiers extraits,
et identité de la fonction via utilisée par le pipeline. Cela ne remplace pas
un essai dans l'interface KiCad. Le ZIP contient toujours le prototype initial,
avec ses pertes connues : l'analyse ci-dessous ne l'a pas modifié silencieusement.

## Méthode causale

Nets112,150,170 de tildagon_base, chaque expérience repartant de la carte source.
Auto gloss intégré, G4 et Centering désactivés, corridor=False. Réduction jusqu'à
une signature inchangée, puis G5. Ce sont des variantes diagnostiques distinctes,
pas des répétitions destinées à mesurer le temps.

On désactive séparément l'arrêt au pad, le nouveau départage des positions à
égalité, puis la progression immédiate après absorption pour expliquer le résidu.
Tous les essais passent G5. Le fichier source est inchangé. Les temps de ces
replays instrumentés ne sont pas utilisés comme benchmark.

| Gain final en mm | Production | Prototype | Sans arrêt pad | Ancien départage | Sans arrêt pad + ancien départage |
|---|---:|---:|---:|---:|---:|
| 112 /I2C/SCL_E | 1,168405 | 0,165713 | 1,168405 | 0,165713 | 1,168405 |
| 150 3V3_SYS | 13,252911 | 12,464038 | 13,244038 | 12,464038 | 13,244038 |
| 170 /ESP_TXD | 1,874619 | 1,450355 | 1,874619 | 1,450355 | 1,874619 |

Le départage des candidats n'explique aucune des pertes étudiées. L'arrêt au pad
explique les deux pertes complètes des nets112 et170 et bloque le mouvement
supplémentaire du net150.

## Net112 : contact latéral préexistant, sans absorption

Via initial (71 ; 99,85), rayon 0,25 mm. Le pad J5 est centré en
(69,825 ; 99,8). KRT mesure 0,175 mm entre le centre du via et le cuivre du pad.
Le rayon du via chevauche donc ce cuivre. `_at_pad` renvoie vrai et le prototype
ignore le via dès le début de G3.1/G3.4, sans annulation préalable de segment.

La production déplace le via à (68,75 ; 99,8) dans G3.4. Désactiver uniquement
l'arrêt pad rétablit ce déplacement et les **1,002691 mm** perdus, avec G5 valide.
C'est une condition d'arrêt trop large par rapport à « segment annulé à une
terminaison pad » ; le simple contact cuivre n'est pas cet événement.

## Net170 : contact après mouvement, les deux segments existent encore

G3.1 déplace le via (125,45 ; 72,575) → (125,635 ; 73,025).
La trace du candidat retenu donne ses ancrages :
(125,635 ; 72,76) et (125,45 ; 73,025). Le nouveau via ne coïncide avec aucun.
Les deux segments mesurent respectivement 0,265 et 0,185 mm : **aucun ne s'annule**.

Le centre du via touche le cuivre de R45, centré en (125,635 ; 73,325), et
`_at_pad` le fige aux traitements suivants. La production le déplace encore à
(125,335 ; 73,325) au deuxième appel. La suppression du seul arrêt pad restitue
ce déplacement et **0,424264 mm**, avec G5 valide.

Ici aussi, l'arrêt a été appliqué sur un contact géométrique alors que la règle
utilisateur visait un événement d'absorption à une terminaison pad.

## Net150 : véritable arrivée sur une terminaison pad

Le via (73 ; 91,35) rejoint (73,7 ; 91,35), centre du pad U33.
Le segment F.Cu reliait exactement ces deux points : il s'annule. Le prototype
s'arrête, conformément à la règle demandée. La production continue ensuite dans
G3.4 jusqu'à (74,25 ; 91,19), avec un résultat final plus court.

La perte de **0,788873 mm** n'est donc pas entièrement un faux arrêt à éliminer :
elle comprend l'effet de l'ancrage explicite demandé au pad. Les déplacements
supplémentaires de production passent KRT/G5, mais ne respectent pas cet arrêt
supplémentaire du prototype.

Contre-expérience : si l'on autorise à nouveau le départ du pad, la progression
immédiate du prototype choisit (74,09 ; 91,35) dans G3.1. Elle restaure 0,780000 mm,
mais laisse 0,008873 mm d'écart par rapport au parcours de production. Désactiver
aussi la progression immédiate restitue exactement **13,252911 mm**, le gain de
production. Réimposer ensuite les connecteurs non vides ne change rien.

Ce résidu appartient à la variante où l'arrêt pad est levé : il montre un effet
de l'ordre des transformations, pas une seconde perte additive indépendante
observée dans le prototype initial déjà arrêté au centre du pad.

## Conclusion et correction à viser

La détection KRT du contact pad n'est pas erronée. C'est son utilisation comme
blocage systématique du via qui est trop large. La règle d'arrêt doit porter sur
**l'absorption réelle d'un segment à sa terminaison pad**, pas sur tout contact
avec le cuivre d'un pad, avant ou après un déplacement sans absorption.

Cela permettrait de corriger les faux arrêts des nets112 et170 sans supprimer
la règle souhaitée sur U33/net150. Le gain supplémentaire de production au-delà
d'U33 doit être distingué d'une non-régression attendue sous cette nouvelle règle.
La reprise immédiate peut également influer sur le résultat lorsqu'elle est
permise ; le résidu de 0,008873 mm en fournit un exemple.

Aucun correctif de comportement appliqué pendant cette analyse. ZIP livré avant
les replays et conservé tel quel. Les outils de diagnostic et leurs données sont
commités séparément de la production.
