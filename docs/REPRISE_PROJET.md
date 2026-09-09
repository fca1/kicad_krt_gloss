# Reprendre Smooth Gloss KRT

UI, dernier correctif : seules les valeurs grid step/budget utilisent la police
Proxi ; titre et libellés gardent la police normale. EB reçoit une largeur
compacte indépendante de sa largeur native courante, appliquée après le layout
via CallAfter (pas de timer). Fenêtre affichée sous Windows : Net 431 px,
EB 54 px, minimum du dialogue 844 px, disposition gauche/droite conservée.

Dernière correction ULPI2_DATA6 : validation des passages sur la chaîne finale
complète, y compris le cuivre inchangé, distincte du sous-ensemble à remplacer.
Portes déplacées et déjà centrées comptées séparément ; deltas nuls omis du log.

État documenté le 8 septembre 2026, refonte `c06a965` puis revue corridor à partir
de `cc758f9` sur `main`,
version du package 0.1.3. Ce guide permet de comprendre les décisions avant
de lire le code concerné par une intervention ; il ne remplace pas cette
vérification ciblée. Vérifier le HEAD et les modifications locales à la reprise.

## Ordre de lecture et autorité des documents

Intégration du 9 septembre 2026 après validation utilisateur du ZIP
`dist/test-supports-e3f5745/KiCadKrtGloss-0.1.3-prototype-supports.zip`
(SHA256 `e6fcc32f7c4614bf17582fb564f8c4f2a2b6146b3b51adb21cedec516bc042fe`) :
les trois modules moteur du ZIP sont repris à l'identique dans les sources.
Le Centering utilise maintenant `support_prototype.py` via `protected_centering`,
sans les anciens replis. Les deux options multiporte et nouveaux segments doivent
être activées. Les supports parallèles sont refusés ; la généralisation des
auto-contacts pendant le mouvement reste à réaliser. La validation sur `/A`
ne vaut pas qualification générale. Le [rapport du prototype](reports/CENTERING_SUPPORT_PROTOTYPE_2026_09_09.md)
conserve les mesures et limites historiques ; son statut non intégré est supersédé
par cette validation utilisateur et cette intégration.

Vérification d'intégration : égalité textuelle des trois modules avec le ZIP.
Tests ciblés : 28 réussites, 3 échecs dans
`test_finite_passages_keep_a_straight_route_under_rotation` (0°, 45°, 90°).
Ces régressions concernent les supports collinéaires refusés par le constructeur
validé sur `/A`. Elles sont conservées visibles, sans adaptation des attentes.
Ne pas annoncer une validation générale du Centering.

Prototype suivant : tag `before_colli` sur `f56597f`, correctif isolé dans
`tools/prototype_collinear_supports.py`. Les 3 tests collinéaires passent avec
ce correctif (37 tests ciblés réussis), `/A` reste identique. La campagne PACK0
est partielle : budgets Centering expirés sur trois cartes, blocage d'import
natif azukar et comparaison CLI sur les deux grosses cartes. Voir le
[rapport collinéaire](reports/COLLINEAR_SUPPORT_PROTOTYPE_2026_09_09.md).
À la demande utilisateur suivante, le constructeur du ZIP collinéaire
`dist/test-colli-7628191/KiCadKrtGloss-0.1.3-prototype-colli.zip`
(SHA256 `41af5552f7e25c0c884b168cde71ca2895148f32e776592d97ad561ddc5a3764`)
est intégré à l'identique dans `dgloss/support_prototype.py`.
Les supports collinéaires compatibles sont maintenant acceptés ; les trois
échecs historiques ci-dessus sont corrigés. Les limites PACK0 et auto-contact
restent applicables. Cette intégration précède le prototype de sélection EB.
Correction des portes isolées : le regroupement de Centering accepte aussi une
porte seule. L'ancien filtre multiporte `len(group) >= 2` supprimait ces cas
avant construction. Régression pipeline complète sous quatre rotations et essai
natif ULPI1_DATA4 sur antmicro__artix_dc_scm : AB20–AB21 centrée, G5 valide.
Voir le [rapport porte isolée](reports/SINGLE_GATE_CENTERING_2026_09_09.md).

Intégration EB du 9 septembre, validée par l'utilisateur :
`kicad_krt_gloss/branch_selection_prototype.py` est maintenant activé au démarrage
normal et inclus avec sa liste et ses images dans le packaging standard. Il mémorise
les branches par net et refuse les références devenues obsolètes ; réimporter
la sélection après remplacement des pistes. Il inclut les copies User pleines
à 0.1 mm, les polices Calculation Settings alignées sur Proxi et deux images
distinctes selon la case EB. Voir le [rapport EB](reports/EB_MEMORY_PROTOTYPE_2026_09_09.md).
La liste du prototype utilise désormais l'adaptateur multicolonne KRG
`branch_scope_list.py` (DataView) : colonne droite compacte « n EB », vide pour
un net entier. Essais natifs Windows : Centering une EB, deux EB, net entier
sans mémoire et EB désactivé ; validation Linux/macOS non effectuée.
Après Add/Replace, une couverture exacte de toutes les pistes non graphiques
du net, avec références et topologie vérifiées, devient un net entier : mémoire
EB retirée et colonne vide. Références manquantes/périmées : aucune promotion.
Les deux champs Calculation Settings partagent désormais le même bord droit.
Le dialogue ne fige plus sa taille d'ouverture comme minimum. General conserve
deux colonnes : netlist à gauche, illustration/EB/calcul à droite, imports sous
la liste. Le basculement vertical de 648e4e6 est retiré après retour utilisateur.
Le résumé EB ne participe plus à une largeur minimale liée aux noms de nets.
Test natif Windows : largeur 1033 → 953 → 1037 → 953 pixels, commandes vérifiées,
polices inchangées. Pas de qualification graphique Linux/macOS.

1. [AGENTS.md](../AGENTS.md) : règles de collaboration et autorisations.
2. Ce guide : état actuel et pièges à connaître.
3. [gloss_rules.md](../dgloss/doc_fr/gloss_rules.md) : spécification fonctionnelle
   de référence ; [gloss_explain.md](../dgloss/doc_fr/gloss_explain.md) en donne
   une présentation accessible.
4. [ARCHITECTURE.md](ARCHITECTURE.md) : responsabilités et durée de vie des données.
5. [KRT_API.md](KRT_API.md) et [PACK0.md](PACK0.md), selon l'intervention.

Les rapports datés dans `docs/reports` décrivent une expérience sur une version
donnée. Leur présence ne prouve pas une intégration. Certains gardent une
conclusion initiale de prototype puis un encart d'intégration ultérieure.
En cas de contradiction, confronter la règle actuelle, le commit et ses tests ;
ne pas transformer une ancienne proposition en comportement attendu.
Les conversations du projet Smooth Gloss KRT expliquent des décisions, mais
une reprise ne doit pas dépendre de leur disponibilité.

## But et contraintes non négociables

Le plugin améliore un routage existant, sans devenir un autorouteur. Il réduit
la longueur et simplifie le cuivre, sous contraintes électriques et géométriques.
Le temps réel est une priorité de conception : éviter la force brute, mesurer
le coût complet, utiliser les index et méthodes KRT. Une accélération qui perd
de la réduction ou de la validité doit être présentée comme un compromis.

KRT est un sous-module externe, non modifiable dans ce projet. Il reste
l'autorité pour les obstacles, distances, clearances et validations électriques.
La façade [krt_api.py](../dgloss/krt_api.py) isole ses imports et adaptations.
Ne pas disperser de nouvelles dépendances directes dans les stratégies.

Les accès inverses de KRG vers les bindings natifs KiCad sont regroupés dans
[`kicad_bridge.py`](../kicad_krt_gloss/kicad_bridge.py). Cette façade ne doit
pas dupliquer l'importeur, les règles ni les validations KRT ; elle délègue ces
opérations à `dgloss.krt_api` et à l'adaptateur d'application validé.

Les relations géométriques doivent rester valables par rotation et réflexion,
sans règles particulières fondées sur l'affichage horizontal ou vertical.
La sortie reste octolinéaire. Les exclusions et éléments protégés définis dans
la spécification ne deviennent pas modifiables par une sélection explicite.

## Subtilités fonctionnelles

**Corridor.** L'onglet Gloss expose la case « Stay in corridor », désactivée par défaut,
avec l'illustration `corridor_illustration.png`. Son état est transmis au Gloss.
Le Centering impose toujours le corridor à son Gloss préparatoire.
Il représente les positions accessibles par une déformation
continue respectant les contraintes à chaque instant. Une destination libre
ne suffit pas : aucun segment, via ou nœud mobile ne peut sauter un obstacle.
Ce n'est ni une bande de largeur constante, ni une région définie par la grille.
L'échec du certificat d'un déplacement particulier ne prouve pas l'impossibilité
de tous les contournements. Voir la définition complète dans `gloss_rules.md`.
Le certificat des pistes utilise désormais des balayages triangulaires à largeur
réelle, sans gonflement ni discrétisation temporelle liée à la grille. Les vias/T
utilisent également ces balayages et les capsules physiques cuivre/percement.
Les refus de grille identifiés ne remplacent plus la validation géométrique.
Les coordonnées construites et les largeurs ne sont plus arrondies pour ces
opérations ; une clé de graphe ne prouve pas une jonction physique. Les fusions
KRT sont proposées sur copie et certifiées avant application (support cuivre et
connectivité), y compris avant l'exemption `geometry_preserving`.
[Correctif, reproduction `/A` et revue des limites](reports/CORRIDOR_ARTIFACT_REVIEW_2026_09_08.md).

**Gloss et Centering.** Ce sont deux actions distinctes. L'action Centering
exécute atomiquement Gloss avec `stay_in_corridor=True`, puis Centering, sans
transformation géométrique ultérieure. Si aucune porte n'est recentrée ou déjà
centrée et certifiée, le Gloss préparatoire est également annulé. Les échecs et
expirations suivent la politique transactionnelle.
Le Centering peut augmenter la longueur. Actuellement ses portes sont pad–pad :
les vias restent des obstacles, mais ne définissent pas de portes via–via ou
pad–via. Cette limitation a été explicitement conservée.

Définition corrigée par l'utilisateur après `a891026` : une porte exige un
entraxe **centre-à-centre ≤ Proxi**, pas une distance cuivre < 2 × Proxi ni une
distance piste–pad < Proxi. Le recentrage maximise la marge dans le passage,
sans imposer cette marge supplémentaire à toute l'approche : seules les
clearances réglementaires s'y appliquent. La construction locale reconnaît la
quantification native de 1 nm et reconstruit des directions exactes sans bouger
les ancres. Le repli sur chaîne complète pour une porte seule, introduit dans
`f41a1b6`, a depuis été retiré : il remplaçait les raccords existants et créait
un coude à 90°. Le déplacement est désormais propagé aux supports voisins
mobiles, dont les intersections avec les rails fixes déterminent les longueurs.
Une proposition inchangée mais centrée et certifiée est un succès géométrique,
pas un motif de reconstruction. Voir le [correctif et les deux reproductions
natives](reports/CENTERING_PROPAGATION_2026_09_08.md).
Le fichier modifié `test_centering2`, SHA-256
`67204b5f58f60fb79f87abbb6e2071a6587fb3ef4c24306b33fe5efe70bbed1a`,
donne une porte U1.1–U1.2 centrée à Y=90,615 mm, +0,6810 mm, G5 valide,
5 pistes remplacées par 5. Test natif détaché :
`tools/reproduce_centering_native.py CHEMIN_PCB`, sans sauvegarde source.
Suite : 408 réussites, toujours le test Centering historique sans porte en échec.
La recherche finie historique de demi-longueurs a été retirée lors de
l'intégration du constructeur par supports validé le 9 septembre.

**Raccourci DHM Centering.** Avec exactement deux pads sélectionnés et aucun
autre objet, le plugin mesure leur entraxe centre-à-centre. Si cet entraxe est
dans la plage Proxi admise (0 à 5 mm), le dialogue s'ouvre sur Centering et
préremplit Proxi avec cette valeur. Les deux pads ne désignent pas les nets à
traiter : la netlist suit la règle commune ci-dessous (aucun net coché
en l'absence de pistes présélectionnées).

**Sélection commune dans KiCad.** Un seul net désigné par les pistes natives
sélectionnées lance toujours le Gloss direct, sans dialogue. Si le dialogue
s'ouvre, ses coches pilotent Gloss et Centering. Sans net présélectionné, aucun
net n'est coché ; avec plusieurs nets présélectionnés, seuls
ceux-ci sont cochés. Le compteur reflète les coches et une liste vide interdit
les deux actions, sans repli implicite sur tous les nets.

Tag de référence avant ce changement : `before_none` sur `caaad2b`.
Après Add/Replace, la liste révèle la première ligne visible modifiée dans son
ordre courant, changement de coche ou de branches mémorisées. Les filtres et
la sélection des lignes restent inchangés ; un ajout en doublon ne défile pas.
Si toutes les lignes modifiées sont filtrées, aucun défilement n'est imposé.

Le dialogue de réglages est non modal et
se ferme avec son éditeur PCB : l'éditeur reste utilisable pour sélectionner
des pistes. La liste commune est située dans General. Ses boutons d'import
ajoutent ou remplacent les coches par les nets des pistes actuellement
sélectionnées ; « Clear selection » vide les coches. Elles pilotent aussi la
surbrillance native des nets sur le PCB, sans modifier la sélection des objets.
La fermeture du dialogue retire cette surbrillance. La sélection visuelle des
lignes de liste est annulée à son ouverture.
Le highlight utilise désormais `SetBrightened` sur les pistes, vias, pads et
zones, état lu par `PCB_RENDER_SETTINGS::GetColor`, puis `Refresh`. Chaque
dialogue mémorise les UUID des objets qu'il a éclairés et ne retire que ces
états ; la sélection native des objets reste intacte. Ce rendu éclaire le
cuivre sans atténuer les autres nets comme le highlight natif de KiCad.
`BOARD.IsHighLightNetON()` ne prouve pas la surbrillance graphique et n'est
plus utilisé. Les essais sur carte détachée ne valident pas le rendu visible.
La version `d896a65` est la référence validée visuellement par l'utilisateur
le 8 septembre 2026 après installation du ZIP
`dist/test-highlight-render-d896a65/KiCadKrtGloss-0.1.3.zip`
(SHA-256 `6c0adafa12a2eb120d209ff188b58f7767d7eff61e378359fa7c9e090d008930`).
Cette confirmation remplace les conclusions prématurées des tests de drapeau
BOARD et de temporisation ; conserver cette implémentation comme base correcte.
Toute simulation temporisée de clic doit rester dans
un outil de test séparé ; aucun timer de highlight ni clic automatique ne
doit être intégré au dialogue de production.
Les deux actions reconstruisent leurs données depuis la carte courante. En mode
branches élémentaires dans le dialogue, Add/Replace mémorise les branches par net.
Les actions utilisent cette mémoire uniquement pour les nets cochés, sans dépendre
de la sélection native ultérieure. Sans mémoire, le net est entier. Une référence
périmée impose une nouvelle importation, sans élargissement silencieux.
La sélection directe sans dialogue conserve son fonctionnement antérieur.
Dans Centering, « Refresh » actualise
Proxi seulement depuis une sélection exacte de deux pads, dans [0, 5] mm.

Dans General, la liste occupe la colonne de gauche ; « Select branch », son
illustration et « Use elementary branches » occupent la colonne de droite,
suivis d'un cadre commun pour les réglages de calcul et la limite d'exécution.
À l'ouverture, le défilement de la liste est au milieu de sa plage.
La barre inférieure contient Gloss, Centering (bleu pâle) et Close ; l'onglet
Centering conserve ses réglages et son statut, sans bouton d'exécution.
Un clic sur Gloss ou Centering affiche immédiatement l'onglet correspondant ;
le Gloss ne bascule plus automatiquement vers Log en fin de traitement.
La boîte de réglages est détachée de l'éditeur
et maintenue au premier plan, mais l'événement de fermeture de l'éditeur la
ferme aussi.

**Longueur et segments.** Leur découpage logiciel ne doit pas devenir une
frontière algorithmique : une réduction peut créer un coude, sa simplification
peut permettre une nouvelle réduction. L'autogloss intégré réexamine les chaînes
complètes localement. Il reste actif quand G4 est désactivé ; il ne garantit pas
l'optimum global. La réduction locale part d'un pad et progresse dans un seul sens.

Après `a49a833`, une famille de réductions de coudes par raccords successifs à
45° complète les raccourcis directs. Ses supports progressent jusqu'au contact
physique KRT ou à une extrémité, avec certificat de surfaces emboîtées, sans
largeur de contrôle ni taille de chanfrein imposée. Elle peut ajouter des segments
pour diminuer la longueur. Avec corridor, les nets modifiés par les étapes
vias/pads/T/fusions sont désormais réexaminés localement avant G5, même sans G4.
Les directions octolinéaires seules ne prouvent pas l'absence de pointe : auditer
aussi les raccordements. Voir [correction et temps PACK0 G3](reports/CORNER_REDUCTION_2026_09_08.md).

**Via mobile.** Le via et les segments incidents des différentes couches doivent
être considérés ensemble. Le corridor de leurs déplacements et le volume du via
doivent être validés. L'absorption d'un segment permet de poursuivre avec le suivant,
sauf arrivée au pad terminal. L'arrêt ne se déclenche pas au simple contact du
rayon du via avec un pad : il exige l'absorption effective jusqu'au pad du même
net sur la couche de la branche, avec la demi-largeur du segment terminal.
L'arrêt est conservé entre étapes et passes du même Gloss, sans verrou permanent
écrit sur la carte. [Correctif et tests](reports/VIA_TERMINAL_ABSORPTION_2026_09_08.md).

**G4.** Le budget initial vaut 20 s et ne borne plus G4. Par défaut,
l'interface autorise une passe supplémentaire (réglable de 1 à 10) ; l'API
conserve sa valeur propre si elle est appelée sans l'interface. Dès la
première, arrêt si le gain incrémental est
inférieur ou égal à 10 % du gain incrémental précédent, comparé d'abord à celui
de la passe initiale. Ce n'est pas 10 % de la longueur restante. Un gain précédent
nul ne déclenche pas le test de ratio ; aucune transformation arrête les passes.
G4 peut continuer après expiration du budget initial : 20 s n'est donc pas un
plafond total. `g4_min_gain_percent` reste interne. Le dialogue expose la case
d'activation G4 et un nombre maximal de passes supplémentaires de 1 à 10 ; ce
réglage ne modifie ni le seuil de gain ni les garanties transactionnelles.
[Définition et validation](reports/G4_LIMITS_2026_09_08.md).

## État des intégrations

| Sujet | État et référence |
| --- | --- |
| Nettoyage des microsegments | Intégré ; [rapport](reports/MICROSEGMENTS_INTEGRATION_2026_09_07.md) |
| Correctifs de réduction et couche KRT | Intégrés ; [rapport](reports/REDUCE_LENGTH_INTEGRATION_2026_09_07.md) |
| Calcul analytique du sens utile du glissement | Intégré ; les recherches adaptatives expérimentales ne sont pas activées par cette intégration ; [rapport](reports/SLIDE_DIRECTION_BUDGET_CACHE_2026_09_07.md) |
| Autogloss sur chaînes complètes | Intégré, sans petites fenêtres ; [rapport avec encart d'intégration](reports/AUTO_GLOSS_2026_09_07.md) |
| Via mobile progressif et faux arrêts | Intégrés ; [prototype](reports/PROGRESSIVE_VIA_2026_09_07.md) et [correctif terminal](reports/VIA_TERMINAL_ABSORPTION_2026_09_08.md) |
| Gloss puis Centering atomique et limites G4 | Intégrés, selon les règles ci-dessus |
| Caches, index KRT et découpage des responsabilités | Intégrés dans `c06a965` ; [architecture](ARCHITECTURE.md) |
| Illustrations du dialogue | PNG fournis dans `kicad_krt_gloss/img_dlg`, inclus dans le package ; aucune construction procédurale de ces illustrations par Python |

Les pistes suivantes ne sont pas une liste de travaux autorisés : elles restent
hors intégration et nécessitent une nouvelle décision pour être reprises.

| Piste | Conclusion utile pour une reprise |
| --- | --- |
| Petites fenêtres autogloss, recherche commune longueur/segments | Non intégrées ; [petites fenêtres](reports/WINDOW_AUTO_GLOSS_2026_09_07.md), [recherche commune](reports/JOINT_GLOSS_2026_09_07.md) |
| Budget de certificat par candidat | Prototype : accélération sur bitaxe avec perte de réduction, aucun gain universel ; [mesures](reports/SLIDE_DIRECTION_BUDGET_CACHE_2026_09_07.md) |
| Cache des fenêtres infructueuses | Très peu de réutilisations, coût propre ; pas de bénéfice convaincant dans les essais du même rapport |
| Grilles plus fines pour certifier le glissement | Expérience observatrice, économies hypothétiques seulement ; raffiner augmente aussi construction et consultations ; [mesures](reports/GRID_RESOLUTION_2026_09_07.md) |
| Ordonnancement G4 par dépendances entre nets | Prototype historique ; ne pas confondre avec le G4 intégré ; [rapport](reports/G4_DEPENDENCIES_PROTOTYPE_2026_09_07.md) |

## Pièges techniques à préserver

- Un raccordement à une extrémité autorisée ne permet pas de recouvrir une
  longueur positive de cuivre collinéaire du même net. Le garde-fou rejette
  désormais ce cas, y compris par rotation/réflexion. Cela ne nettoie pas les
  chevauchements déjà présents : sur `test_centering2`, `/A`, corridor actif,
  le fichier SHA-256 `02444ca7e2856235f09683a66ef85a7206e1280926a436f780a5c1019d133cec`
  restait à 63,4121 mm après le seul garde-fou anti-recouvrement. Le remplacement
  ultérieur du certificat de corridor répare maintenant cet instantané :
  60,5921 mm, 8 → 7 pistes, zéro paire en recouvrement, sortie octolinéaire et
  G5 valide. Ce premier résultat conservait toutefois une pointe : le correctif
  suivant atteint 54,594283 mm, 9 pistes, zéro recouvrement et zéro pointe sur `/A`.
  Le test natif est reproductible par `tools/reproduce_corridor_fold.py` et vérifie
  désormais les raccordements et les coordonnées après application native.
  Le fichier source n'est pas sauvegardé ; ce n'est pas une validation visuelle.
- Demande de sauvegarde après simple ouverture : KiCad 10
  `PCB_EDIT_FRAME::RunActionPlugin` appelle `OnModify()` lorsque son instantané
  d'annulation contient des objets, sans vérifier leur modification effective.
  Voir [le code KiCad 10](https://github.com/KiCad/kicad-source-mirror/blob/10.0/pcbnew/python/scripting/pcbnew_action_plugins.cpp).
  Détacher la fenêtre ne corrige pas ce comportement. Ne pas effacer aveuglément
  l'état modifié, ni déclencher Undo ou une sauvegarde automatique pour le masquer.
  Cette limite de l'intégration ActionPlugin reste non résolue.
- Cache Rust Windows : réutiliser un binaire dont le SHA-256 correspond, même
  si une réinstallation a changé sa date. Une extension chargée est verrouillée ;
  ne jamais la recopier pour une simple différence d'horodatage. Les copies
  nécessaires sont publiées par remplacement atomique depuis un fichier temporaire.
- `segment_blocked` à marge zéro ne démontre pas le balayage du déplacement :
  dans le chemin KRT étudié, seule l'arrivée était testée. Une marge positive
  minuscule ou `pas/2` ne constitue pas à elle seule une preuve de corridor.
  Distinguer clearance physique, réserve de discrétisation et enveloppe balayée.
  Ne pas réintroduire une constante de 0,3 mm comme correction universelle.
  [Expérience sur les enveloppes](reports/RUST_SLIDE_ENVELOPE_2026_09_07.md).
- Une grille conservatrice peut refuser un déplacement pourtant valide ; cela
  réduit les possibilités. Une réponse libre utilisée comme certificat exige
  une justification couvrant les arrondis et toute la géométrie déplacée.
- Les caches suivent un état de cuivre précis. Les segments et vias sont remplacés
  par de nouveaux objets, sans mutation en place. Appliquer les remplacements
  validés par `GlossContext.apply_replacement` et respecter les rafraîchissements
  d'obstacles ; voir [la durée de vie des données](ARCHITECTURE.md).
- Une mutation d'un autre net peut affecter les zones : elle invalide aussi les
  certificats électriques de référence. Les candidats et G5 restent recalculés.
- Une restauration doit remettre le cuivre et invalider ses données dérivées,
  dont les modèles de zones ; restaurer les seules listes de segments ne suffit pas.
- Les copies de moteurs dans `tools` peuvent être des références historiques.
  Leur comportement ne décrit pas nécessairement la production.
- Une lenteur observée dans KiCad peut venir de l'application native du résultat :
  le problème de largeur de pad KiCad 10 a notamment nécessité `GetFrontWidth()`
  avec repli compatible. Mesurer moteur et application séparément.

## Validation disponible et limites connues

La campagne hors PACK0 sur `4d14d3b` ne valide pas une absence globale
d'artefacts : coude résiduel après glissement local sur `usbc_power_adapter`
(`/USB PD/CC2`), exclusion des arcs non effective sur `usb_dali` (`/USB+`,
application native refusée), six alertes complémentaires de clearance à
qualifier sur `bitaxe_ultra`. Les budgets expirés restaurent les entrées.
Ces points ne sont pas corrigés dans le ZIP issu de cette campagne.
Voir le [bilan hors PACK0](reports/CENTERING_OUTSIDE_PACK0_2026_09_08.md).

La campagne historique du 8 septembre après refonte a donné **299 tests réussis et quatre
échecs préexistants**, reproduits avant modification : ancien inventaire refusant
`AGENTS.md`, explication française sans traduction anglaise, contrôle textuel de
dépendance refusant l'accès optionnel à `NetSelectionPanel`, et
`test_a_later_gloss_completely_removes_a_longer_centering_path` sans porte centrée.
La revue corridor donne désormais **369 réussites et un échec préexistant**,
le test Centering sans porte centrée. Ne pas annoncer une suite entièrement verte.

La correction des pointes donne ensuite **399 réussites et le même échec
Centering**. PACK0 sans G4 passe les dix configurations avec/sans corridor,
sans nouvelle pointe détectée hors ancres. Un raccord aigu préexistant subsiste
sur tildagon net 150 ; aucune garantie d'absence globale d'artefacts n'est revendiquée.

PACK0 contient cinq cartes fixes avec empreintes dans [PACK0.json](PACK0.json).
La comparaison de refonte conserve exactement les géométries sur les quatre
cartes réussies, avec environ 5 à 9 % de temps en moins sur des mesures uniques.
Dans cette ancienne campagne, `azukar_fpga` échoue et restaure la carte : ce n'est pas une
validation fonctionnelle réussie. Le rapport initial PACK0 signalait une
régression de connectivité sur le net 11 ; ne pas attribuer sans diagnostic
tout nouvel échec à cette même cause.

La nouvelle campagne corridor traite les cinq cartes avec et sans corridor,
avec contrôle indépendant des nouvelles directions, et réussit notamment sur
`azukar_fpga` après rejet des propositions de fusion électriquement invalides.
Les géométries et les gains changent ; ne pas confondre validité géométrique et
non-régression de rendement. Voir les mesures, les pertes de gain explicites et
les limites dans le [rapport corridor](reports/CORRIDOR_ARTIFACT_REVIEW_2026_09_08.md).

Les tests natifs sur `test_centering2` ont aussi validé moteur et application
sur une carte détachée. Cette carte locale évolue : enregistrer son empreinte,
ne pas identifier une référence par son seul nom ou le label B.
[Rapport de refonte et mesures](reports/ARCHITECTURE_REGRESSION_2026_09_08.md).

Un G5 valide n'est pas un DRC KiCad complet, ni une validation d'installation
sur toutes les plateformes. Une mesure sous profileur n'est pas un temps réel
représentatif ; une économie de validation potentiellement évitable n'est pas
une accélération réalisée.

## Procédure pratique de reprise et d'évolution

1. Lire les règles, vérifier branche, HEAD, état local et révision KRT. Préserver
   les fichiers préexistants, y compris les expériences non suivies par Git.
2. Définir une hypothèse et des critères distincts : résultat géométrique,
   validité électrique, temps. Comparer des versions et configurations identifiées.
3. Après le « go », modifier la zone concernée et lancer les tests ciblés.
   Le bootstrap de test utilisé dans cet environnement est :

   ```powershell
   python -c "from kicad_krt_gloss.runtime import configure_krt_runtime; configure_krt_runtime(); import dgloss, pytest; raise SystemExit(pytest.main(['tests/test_architecture.py']))"
   ```

   Précharger `dgloss` évite les réimports du runtime provoqués par certains mocks.
   Pour les essais natifs, utiliser le Python de KiCad ; son emplacement local
   constaté est `D:/kicad/bin/python.exe`, à vérifier sur un autre poste.
4. Pour une campagne demandée, utiliser les cartes connues et leurs empreintes.
   « Plusieurs tests » signifie plusieurs cartes, sans répétitions ni préchauffage
   sauf demande contraire. Ne pas sauvegarder les PCB sources. Rapporter budget,
   corridor, G4, périmètre chronométré, gain, statut et `nets/s` ; séparer parsing,
   moteur avec contexte/G5, et application native. Voir le protocole PACK0.
5. Conclure explicitement : intégré, abandonné ou en attente. Mettre à jour ce
   guide et les règles affectées, conserver le rapport de mesure, puis faire un
   commit dédié sans les autres changements locaux.
6. Créer un ZIP uniquement sur demande. Tester le package exact produit et ses
   ressources ; ne pas déduire sa validité de la seule réussite des sources.
   Ne pas annoncer un succès CI sans vérifier que les erreurs remontent au statut.

Ce guide doit évoluer avec les intégrations. Les chiffres ci-dessus restent
datés ; toute nouvelle campagne doit préciser ce qu'elle remplace ou confirme.
