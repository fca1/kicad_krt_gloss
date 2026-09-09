# Prototype de mémoire EB — 9 septembre 2026

## Statut actuel : intégré

À la demande utilisateur « on intègre », activation au démarrage standard dans
`__init__.py`, inclusion des deux modules EB et de l'image net entier dans
`package_pcm.py`. KRT inchangé. Le nom historique du module prototype est conservé.
Les mentions d'activation optionnelle ci-dessous décrivent les essais antérieurs.
Les limites restent applicables : mémoire de dialogue, réimport après remplacement
des pistes partielles, validation native Windows seulement.

Validation d'intégration : 75 tests ciblés réussis. ZIP standard
`dist/integrated-eb-a82be9a/KiCadKrtGloss-0.1.3.zip`, SHA256
`001dd706b81561b09c7570a3d3c75478ba007816dee3783ecf53e5447b2f675e`.
Démarrage du package extrait vérifié ; Centering avec promotion de toutes les EB
au net complet réussi depuis ce package (3 portes, G5 vrai, source inchangée).

Le correctif collinéaire testé par ZIP a été intégré préalablement dans ed31e59.
Ce nouveau prototype est isolé : appeler `branch_selection_prototype.activate(action_plugin)`.
La fonction renvoie une restauration des branchements temporaires.
Il n'est pas activé par le démarrage normal des sources ; le ZIP de test ci-dessous l'active.
Un futur ZIP doit inclure le module, la nouvelle image et l'activation explicite.
Il doit aussi inclure `branch_scope_list.py`, adaptateur de liste multicolonne.

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

## Ajout de la colonne EB

Le prototype remplace uniquement l'instance de liste du panneau par un
`wx.dataview.DataViewListCtrl`, sans modifier KRT. Adaptateur KRG conservant
les opérations du panneau (coches, lignes sélectionnées, filtres et boutons).
Le nom du net reste dans sa colonne ; la colonne droite « EB » contient
« n EB », ou une chaîne vide pour le net entier. EB désactivé masque les
comptes sans effacer la mémoire. Une ligne décochée conserve son compte mémorisé.

Largeur demandée : 50 unités logiques, augmentée uniquement si nécessaire pour
le texte et sa marge ; le nom du net occupe l'espace restant. Sur Windows le
contrôle ajoute une petite bordure (54 pixels constatés pour 2 EB à DPI 100 %).
Pas de personnalisation de police/couleur dépendante de Windows.
Référence API : https://docs.wxpython.org/wx.dataview.DataViewListCtrl.html
Linux et macOS non exécutés : compatibilité visée, pas qualification annoncée.

Nouvelle vérification native sur la même empreinte source, sans sauvegarde :

| Centering /A, Proxi 2.54 | Résultat | Temps moteur annoncé |
| --- | --- | --- |
| Une branche mémorisée | 3 portes, G5 vrai | 108.0 ms |
| Deux branches mémorisées | 3 portes, G5 vrai | 107.5 ms |
| Net entier, EB coché sans mémoire | 3 portes, G5 vrai | 114.3 ms |
| Net entier, EB décoché avec mémoire dormante | 3 portes, G5 vrai | 108.3 ms |

Chaque exécution réimporte une carte neuve, vérifie le nombre exact de segments
transmis et compare UUID/géométrie/largeur de toutes les pistes hors périmètre.
Les quatre cas produisent ici le même recentrage (7 pistes vers 7) : les portes
concernées sont dans la première branche ; ce n'est pas un test de deux branches
portant chacune une porte indépendante. Les coordonnées hors périmètre restent
inchangées. La sélection native ultérieure différente est ignorée.

Le runner accepte `--scope single|multiple|whole|eb-off`. Il teste également
les événements de coches du nouveau composant, boutons d'action, largeur compacte,
comptes après filtrage et basculement EB. Gloss une branche passe également.
Les 71 tests ciblés précédents restent verts. Ce contrôle ne valide pas le rendu
visible de l'éditeur ni toutes les combinaisons multi-net et toutes les cartes.

## ZIP de test demandé

`dist/test-eb-4b3b9b4/KiCadKrtGloss-0.1.3-prototype-EB.zip`

SHA256 : `1169d30c0de1e3c26fa79370da2dd86c4f5bec2a9098f70aff8b3e657b994574`.
Construction reproductible par `tools/package_branch_memory.py` : sources normales
plus modules EB, seconde image et activation avant l'enregistrement du plugin.
Intégrité ZIP et égalité des ressources contrôlées. Démarrage réel du package
importé testé (seul l'enregistrement dans KiCad est neutralisé) : BranchDialog et
préparation EB actifs. Test natif Centering deux branches exécuté depuis le ZIP
extrait via `KRG_TEST_PLUGIN_ROOT` : réussi, 3 portes, G5 vrai, hors périmètre
préservé et source inchangée. Ce test ne constitue pas une installation PCM
interactive ni une qualification Linux/macOS.

## Évolution après ce ZIP : net complet et alignement

Après Add/Replace (et capture initiale), comparer l'union des UUID mémorisés
aux pistes non graphiques du net importé courant. Exiger une couverture complète
des segments par l'index et vérifier les branches avec la résolution habituelle.
Si tout correspond, supprimer la mémoire de ce net : il devient explicitement
un net entier, y compris pour les actions suivantes ; la colonne EB est vide.
Une mémoire périmée ou un index incomplet ne provoque jamais cette promotion.
Ce contrôle n'utilise pas seulement le nombre de segments ou de branches.

Calculation Settings utilise une grille commune : libellés à gauche, champs
de même largeur et même bord droit, colonne d'unité réservée pour « s ».
Il s'agit de l'alignement des champs, sans modification des valeurs de calcul.

### Correction du redimensionnement après intégration

Les appels Fit puis SetMinSize(GetSize) transformaient la largeur calculée en
minimum irréductible. Ils sont remplacés par une taille d'ouverture distincte
du minimum de la disposition compacte. General est un ScrolledWindow vertical ;
les colonnes et boutons d'import s'empilent lorsque le contenu ne tient plus.
Le seuil est calculé depuis les sizers ; les polices agrandies restent inchangées.
Le résumé des branches ne fait plus croître le minimum avec les noms des nets ;
le texte complet reste disponible en infobulle et la colonne EB reste présente.

Test natif Windows : réduction réelle 960 → 536, agrandissement 1037 puis retour
536 pixels, vérification des orientations, champs dans la largeur disponible
et boutons d'exécution dans la fenêtre. Centering net complet et Gloss deux EB
passent après réduction, G5 vrai, source inchangée. Le test textuel historique
exigeant SetSizerAndFit est mis à jour : il protégeait l'ancien dimensionnement.
Ces tests ne constituent pas une validation visuelle utilisateur sur les trois OS.

74 tests ciblés réussis. Runner natif étendu avec `--scope complete` : Replace
de toutes les EB puis Add successifs jusqu'à couverture complète, cellule vide,
Centering effectif /A à Proxi 2.54, 3 portes, G5 vrai, source inchangée.
Gloss net complet et Centering deux EB passent aussi. Le test natif compare
les bords droits des deux champs. Le ZIP précédent n'inclut pas cette évolution.
