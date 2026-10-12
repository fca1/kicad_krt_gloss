# Réductions issues de la comparaison complete1 / Fusion

## Diagnostic établi avant correction

Référence du moteur précédent : `10f4b56edb32c26d82d9a79981456e942e83a145`.
Les deux BRD sont lus sans modification. `complete1` est importé avec le lecteur
EAGLE natif KiCad 10, dans un nouveau fichier de travail : 683 pistes, 117 vias,
4 008,3756 mm. Le repère inverse Y et arrondit aux unités natives du nanomètre.
Le moteur reçoit les 47 nets routés, tous les autres cuivres restant obstacles.

- **CHARGE+** : les chaînes homogènes arrêtent la recherche à la transition
  1,4/1 mm en (101,6 ; -52,07). Le candidat vers (101,6 ; -50,8) réduit de
  1,796051 mm. Clearance KRT, garde électrique et mouvement continu acceptent
  ce candidat avant modification. Les recherches séparées ne le construisent pas.
- **N$11** : le départ de TP414 comporte un segment entièrement dans le pad et
  un joint touché par deux segments. Le décompte des extrémités le classe comme
  plusieurs entrées et `_walk_terminal_chain` renvoie `None`. Une fois le départ
  reconnu, le raccord complet reste bloqué ; un préfixe de trois segments peut
  être réduit de 0,387238 mm avec les trois mêmes validations KRT.
- **Glissement fin** : un cas synthétique avec obstacle à Y=3,537 accepte un
  déplacement de 1,236 mm, mais l'ancienne recherche s'arrête à 1,2 mm. Le gain
  passe de 0,994113 à 1,023936 mm avant toute modification du moteur.
- **Écriture** : la première version affinée a produit un contact `CHARGE-`
  valide en mémoire mais refusé après arrondi d'écriture. La recherche vérifie
  désormais aussi les coordonnées arrondies à six décimales en millimètres.

Ce diagnostic explique les cas reproduits sur la version courante. Il ne
reconstitue pas la version, la sélection ou les paramètres de l'action initiale
effectuée par l'utilisateur. Aucun journal de cette action n'a été retrouvé.

## Modifications

`width_transitions` propose une famille locale de trois segments : les supports
extérieurs se rencontrent à la nouvelle transition ; le segment central peut
disparaître seulement s'il partage la largeur de l'un des voisins. Pas de
réduction d'une largeur distincte, pas de déplacement de pad/via/jonction,
pas de modification hors portée. Le mouvement est certifié pour chaque largeur,
même si l'option corridor est inactive. Chaque application invalide les caches
via `GlossContext.apply_replacement` et les chaînes sont ensuite réexaminées.

Le parcours depuis un pad distingue une seule chaîne simple avec contacts
internes de plusieurs entrées indépendantes. Une branche, un via, un verrou
ou un retour ultérieur au pad restent conservateurs. Si le raccord au dernier
point fixe échoue, les préfixes sont examinés depuis le pad dans un seul sens ;
le suffixe reste un obstacle et une ancre.

Le glissement conserve son parcours initial par pas, puis raffine uniquement
le dernier intervalle par au plus 24 dichotomies (tolérance 0,0000001 mm).
Chaque candidat exact et sa version arrondie passent KRT. Le seuil de gain
supérieur au pas reste inchangé. Ce sondage n'est pas en lui-même une preuve
de corridor ; les voies qui exigent le corridor conservent leurs certificats.
La réduction locale en mode corridor n'utilise pas cette nouvelle recherche.

Aucun réglage public ajouté, aucune source KRT modifiée.

## Essais comparables sur complete1

Une passe du moteur, budget 20 s, G4 désactivé, grille 0,1 mm,
clearance 0,1524 mm, bord 0,3 mm, trous 0,254 mm. Les mêmes paramètres,
le même import et le même ordre des nets sont utilisés avant/après. Les mesures
ne comprennent pas un nouveau lissage KRT préliminaire du plugin natif.

| Mode | Gain précédent | Gain corrigé | Segments avant/après correction | Temps précédent/corrigé |
|---|---:|---:|---:|---:|
| Vias fixes, corridor désactivé | 2,6267 mm | 8,4176 mm | 662 / 655 | 1,69 / 4,94 s |
| Vias fixes, corridor activé | 0,8870 mm | 4,0446 mm | 663 / 657 | 1,14 / 2,25 s |
| Vias mobiles, corridor désactivé | 7,7994 mm | 13,5903 mm | non relevé dans le résumé CLI | 1,98 / 5,15 s |

G5 valide dans les six essais, sans expiration du budget. Les temps sont ceux
d'un essai par configuration, pas une campagne statistique de performance.
Le coût supplémentaire des contrôles et des préfixes est mesurable.

À vias fixes, le gain supplémentaire est **5,7909 mm**. `CHARGE+` récupère
1,796051 mm et `N$11` 0,387238 mm, y compris en mode corridor. `N$18` perdait
déjà ses deux segments à longueur égale avant correction ; seul son affinement
supplémentaire de 0,110678 mm est nouveau. `N$8` reste pratiquement inchangé :
aucune prétention de convergence globale ni de récupération de tous les gains Fusion.

Fusion avait gagné 7,381325 mm et conservé 671 segments, avec 117 vias inchangés.
La sortie corrigée à vias fixes mesure 3 999,957931 mm avec 655 segments et
117 vias inchangés, soit environ 1,0363 mm de moins que cette sortie Fusion.
Les interprétations complètes des règles des deux applications ne sont pas
certifiées équivalentes : ceci compare des résultats sur cette carte, pas les
performances générales des deux produits.

## Contrôles de sécurité et de sortie

272 tests ciblés passent en 1,51 s : régressions nouvelles, rotations par 45°
et réflexions, obstacles, géométrie, verrouillage, pads/vias fixes, périmètre
partiel, garde électrique, corridor, autogloss, caches, fusions et G4.
Un ancien test imposant un résultat sur grille contrôle désormais la clearance
réelle du chanfrein, qui peut être affiné hors grille.

La sortie native a été réimportée : 655 segments et 117 vias, longueur conforme
au résultat en mémoire à la précision d'écriture. Les **93 nouveaux segments**
passent à nouveau la clearance KRT ; les partitions électriques des 47 nets
routés sont identiques à celles de l'entrée. Le nombre de segments existants
inférieurs à `0,1 mm - 1e-9` reste 106 ; aucune promesse d'effacement des petits
raccords ajoutés par la conversion. G5 vérifie l'absence de nouveaux microsegments.

Les vérifications ne constituent pas un DRC KiCad/Fusion complet, un test natif
interactif du dialogue, une installation du plugin ou une campagne PACK0.
Les limites connues de KRT concernant certains balayages de vias restent présentes.

## Traces locales

Dans `C:/Users/frant/Downloads/cube_pcb1/comparaison_gloss_20261012/` :

- `validation.py` : essais à vias fixes, ancien moteur chargé depuis la révision
  Git indiquée, puis moteur courant ; aucune réécriture des sources.
- `baseline_fixed_vias.json`, `after_fixed_vias.json`, `baseline_corridor.json`,
  `after_corridor.json` : résultats et métriques par net.
- `baseline_all.json`, `after_all.json` : essais CLI avec mobilité des vias.
- `verification_sortie.json` : contrôle après écriture et relecture.
- `complete1_gloss_ameliore.kicad_pcb` : carte de comparaison à vias fixes.

Empreintes SHA-256 :

```text
complete1.brd : f60e0465e7d535f15c28aa40944bff6d61b59c247e1c46e1c2cd4fb297b3e382
smoothed.brd  : 86976c1e718af7c390ac92b33250dc35b7b77194e755e73880e348c2d998182e
sortie KiCad  : 2b0b033894cd20b5e6ce2c5189f38823a928d0977239ba2d177ca59b03f4ce98
```

Les deux BRD sources conservent leurs empreintes initiales. Aucun ZIP créé.
