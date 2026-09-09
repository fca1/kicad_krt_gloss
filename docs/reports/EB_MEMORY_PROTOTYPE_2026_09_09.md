# Prototype de mémoire EB — 9 septembre 2026

Le correctif collinéaire testé par ZIP a été intégré préalablement dans ed31e59.
Ce nouveau prototype est isolé : appeler `branch_selection_prototype.activate(action_plugin)`.
La fonction renvoie une restauration des branchements temporaires.
Il n'est pas activé par le démarrage normal ; aucun ZIP EB produit à ce stade.
Un futur ZIP doit inclure le module, la nouvelle image et l'activation explicite.

## Règles

- EB décoché : nets cochés entiers ; mémoire conservée en sommeil.
- EB coché : branches mémorisées par net ; sans mémoire, net entier.
- Add importe les branches complètes des pistes sélectionnées et les cumule sans doublon.
- Replace remplace la mémoire et les nets cochés. Replace avec EB décoché efface la mémoire.
- Cliquer un net affiche son périmètre mémorisé sans le modifier.
- Gloss et Centering utilisent cette mémoire, pas la sélection native ultérieure.
- Clear efface la mémoire. Elle ne survit pas à la fermeture du dialogue.
- UUID supprimé, remplacé ou topologie modifiée : action refusée, réimport requis.
  Cela concerne aussi une deuxième action après transformation des pistes mémorisées.
  Aucun élargissement silencieux au net entier.

Le surlignage partiel cible pistes et vias associés, sans changer IsSelected.
Les états de surbrillance préexistants sont préservés. Un résumé indique le nombre
de branches par net sans modifier les noms dans la liste.

## Présentation

Les nouveaux segments pleins User sont à 0.1 mm, indépendamment de la largeur CU.
Les anciens pointillés et marqueurs de vias restent inchangés.
Calculation Settings / Execution Limit utilise la taille de Proxi (14 points).
Deux fichiers indépendants : `selection_scope_illustration.png` reste intact
pour EB coché ; `selection_net_illustration.png` représente le net entier pour
EB décoché. La case échange les bitmaps préchargés, sans retouche de l'image.
La seconde image est adaptée aux dimensions d'affichage de la première au chargement.

La compétence imagegen a servi à créer uniquement la seconde image via l'outil
intégré, sans éditer la première. Consigne : diagramme sombre 220:106, texte
« Selected net », trois pads dorés aux positions (35,70), (108,70), (185,40),
deux segments cyan identiques, aucun rectangle ni trait pointillé.
Fichier : `kicad_krt_gloss/img_dlg/selection_net_illustration.png`.

## Vérification

71 tests réussis : test_branch_memory_prototype, test_plugin_boundaries,
test_protected_centering, test_prototype_collinear_supports.

`tools/check_branch_memory_native.py` exécuté avec le Python KiCad pour chacune
des actions `--action gloss` et `--action centering` sur test_centering2.
Vérifie Add/Replace/Clear, absence de doublons, clic netlist, UUID surlignés,
sélection native inchangée, périmètre malgré une sélection native différente,
refus des références périmées, polices et pixels après événements checkbox EB.
Vérifie aussi les géométries hors branches inchangées et les copies User à 0.1 mm.

Centering : 3 portes, 7 pistes vers 7, G5 vrai, 112.7 ms.
Gloss (corridor désactivé) : 13 pistes vers 2, 37.4697 mm gagnés, G5 vrai, 91.4 ms.
Ces mesures sont des essais ciblés, pas une campagne PACK0.

Carte chargée en mémoire, jamais sauvegardée. Empreinte source inchangée :
`08b5d8efe0990e9753f111b680fd1d95cf6ddb78e82888aa09182422c8f797fb`.
Les avertissements wx existants (parentage, gestionnaires images et fermeture)
restent présents. Les contrôles natifs ne remplacent pas une validation visuelle
utilisateur dans l'éditeur KiCad ouvert.
