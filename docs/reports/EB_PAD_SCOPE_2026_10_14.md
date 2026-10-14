# Faux refus de topologie EB — 14 octobre 2026

## Cause et correction

Sur une carte synthétique inchangée, deux segments jointifs de 0,1 et 0,4 mm
passent près d'un pad dont seul le segment large touche le cuivre. Le parcours
depuis le segment étroit incluait les deux segments ; celui depuis le large
s'arrêtait au pad. Selon l'ordre des graines, la même union comptait une ou
deux branches. `BranchMemory.resolve` exige une branche unique et refusait
donc une mémoire venant d'être capturée. La promotion d'une sélection totale
en net entier appelle ce même contrôle et échouait également.

Le parcours vérifie maintenant le contact avec le pad de chaque côté de la
jonction, avec la couche, la position réelle de l'extrémité et la demi-largeur
du segment concerné. Le même défaut à travers un via vers un pad présent sur
l'autre couche est couvert. Le calcul de l'extrémité de sortie est commun
aux parcours avec et sans changement de couche.

KRT reste l'autorité pour la distance au pad. Aucun contrôle de mémoire
périmée n'est supprimé ; les sélections partielles restent limitées.
Le défaut est reproduit indépendamment de la carte utilisateur, dont le
chemin n'a pas été communiqué. Son attribution à cette carte précise reste
donc à confirmer lors de la recette utilisateur.

## Revue et validation

Revue selon `review-agent` du diff entier et de ses appels : capture native,
résolution EB, promotion complète et portée transmise au pipeline Gloss.
Aucun défaut introduit supplémentaire identifié. Pas de refonte générale
ni de modification de KRT.

- 32 tests ciblés réussis : `test_elementary_branches.py`,
  `test_branch_memory_prototype.py`, `test_kicad_boundary.py`.
- Régression testée dans les deux ordres de capture, en rotation 0/45/90°,
  en réflexion et à travers un via vers un pad sur l'autre couche.
- Essai avec `D:/kicad/bin/python.exe`, carte construite en mémoire : import
  KRT, index UUID, capture de deux branches, nouvelle importation, résolution,
  promotion entière, puis sélection du seul segment étroit sans élargissement.
  Réussi depuis les sources et depuis le plugin installé. Aucun PCB sauvegardé.
- Suite `tests` et `dgloss/tests` : 562 réussites, un xfail connu, un échec
  dans `test_lazy_resolution_preserves_identity_and_resolves_once`. Ce test
  attend `kicad_parser` au lieu de `_gloss_embedded_krt.kicad_parser` ; même
  échec confirmé avec le parcours de branches de HEAD avant correction.

La suite historique utilise encore des imports KRT plats. Avec le seul
bootstrap du guide, la collecte complète échoue sur `kicad_parser` et un
second chargement PyO3. Pour la mesure complète ci-dessus, les noms plats des
modules KRT privés déjà chargés ont été associés aux mêmes objets uniquement
dans le processus de test. Cette compatibilité ne modifie pas le plugin et
ne constitue pas une recette de coexistence entre plugins. Sans cette
compatibilité, trois tests de contacts dans `test_architecture.py` échouent
aussi avant correction en raison du mélange des imports historiques.

Pas de DRC complet ni de recette interactive sur la carte utilisateur.
La validation native couvre la sélection et l'import, pas un Gloss complet.

## Installation locale

Éditeur PCB fermé, sauvegarde complète du plugin dans :

`C:/Users/frant/Documents/KiCad/plugin-backups/kicadkrtgloss-before-eb-pad-scope-20261014-095455`

Seul `dgloss/branches.py` remplacé dans
`C:/Users/frant/Documents/KiCad/10.0/3rdparty/plugins/com_github_fca1_kicadkrtgloss`.
SHA-256 contrôlés :

- Ancien : `43121c809c3ed2cad3a462c6510dd0015db5195cf8517ae140f1260169631268`.
- Nouveau : `b785f490ee4dc770ccaa14d121951cfd066989d7bddb90bdadf3555eccdc9aaa`.

Rouvrir l'éditeur PCB pour charger la correction. La version reste 0.1.4 ;
aucun ZIP, aucune publication. Pour revenir en arrière, fermer l'éditeur puis
restaurer ce fichier depuis la sauvegarde.
