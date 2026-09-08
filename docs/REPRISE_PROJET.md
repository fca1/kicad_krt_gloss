# Reprendre Smooth Gloss KRT

État documenté le 8 septembre 2026, moteur de référence `c06a965` sur `main`,
version du package 0.1.3. Ce guide permet de comprendre les décisions avant
de lire le code concerné par une intervention ; il ne remplace pas cette
vérification ciblée. Vérifier le HEAD et les modifications locales à la reprise.

## Ordre de lecture et autorité des documents

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

**Corridor.** Il représente les positions accessibles par une déformation
continue respectant les contraintes à chaque instant. Une destination libre
ne suffit pas : aucun segment, via ou nœud mobile ne peut sauter un obstacle.
Ce n'est ni une bande de largeur constante, ni une région définie par la grille.
L'échec du certificat d'un déplacement particulier ne prouve pas l'impossibilité
de tous les contournements. Voir la définition complète dans `gloss_rules.md`.

**Gloss et Centering.** Ce sont deux actions distinctes. L'action Centering
exécute atomiquement Gloss avec `stay_in_corridor=True`, puis Centering, sans
transformation géométrique ultérieure. Si rien n'est centré, le Gloss préparatoire
est également annulé. Les échecs et expirations suivent la politique transactionnelle.
Le Centering peut augmenter la longueur. Actuellement ses portes sont pad–pad :
les vias restent des obstacles, mais ne définissent pas de portes via–via ou
pad–via. Cette limitation a été explicitement conservée.

**Raccourci DHM Centering.** Avec exactement deux pads sélectionnés et aucun
autre objet, le plugin mesure leur entraxe centre-à-centre. Si cet entraxe est
dans la plage Proxi admise (0 à 5 mm), le dialogue s'ouvre sur Centering et
préremplit Proxi avec cette valeur. Les deux pads ne désignent pas les nets à
traiter : la netlist suit la règle commune ci-dessous (tous les nets admissibles
cochés en l'absence de pistes présélectionnées).

**Sélection commune dans KiCad.** Un seul net désigné par les pistes natives
sélectionnées lance toujours le Gloss direct, sans dialogue. Si le dialogue
s'ouvre, ses coches pilotent Gloss et Centering. Sans net présélectionné, tous
les nets admissibles sont cochés ; avec plusieurs nets présélectionnés, seuls
ceux-ci sont cochés. Le compteur reflète les coches et une liste vide interdit
les deux actions, sans repli implicite sur tous les nets.

Le dialogue de réglages est non modal et
se ferme avec son éditeur PCB : l'éditeur reste utilisable pour sélectionner
des pistes. La liste commune est située dans General. Ses boutons d'import
ajoutent ou remplacent les coches par les nets des pistes actuellement
sélectionnées ; « Clear selection » vide les coches. Elles pilotent aussi la
surbrillance native des nets sur le PCB, sans modifier la sélection des objets.
La fermeture du dialogue retire cette surbrillance. La sélection visuelle des
lignes de liste est annulée à son ouverture.
Le highlight reste défectueux dans l'éditeur : `BOARD.IsHighLightNetON()`
ne prouve pas la surbrillance graphique. Les essais sur carte détachée ne
valident pas le rendu. Toute simulation temporisée de clic doit rester dans
un outil de test séparé ; aucun timer de highlight ni clic automatique ne
doit être intégré au dialogue de production.
Les deux actions reconstruisent leurs données depuis la carte courante. En mode
branches élémentaires, les pistes natives désignent les branches uniquement de
leurs nets cochés ; un net coché sans graine native désigne tout son cuivre.
Les graines d'un net décoché sont ignorées. Dans Centering, « Refresh » actualise
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

La campagne du 8 septembre après refonte a donné **299 tests réussis et quatre
échecs préexistants**, reproduits avant modification : ancien inventaire refusant
`AGENTS.md`, explication française sans traduction anglaise, contrôle textuel de
dépendance refusant l'accès optionnel à `NetSelectionPanel`, et
`test_a_later_gloss_completely_removes_a_longer_centering_path` sans porte centrée.
Ne pas annoncer une suite entièrement verte sur cette base.

PACK0 contient cinq cartes fixes avec empreintes dans [PACK0.json](PACK0.json).
La comparaison de refonte conserve exactement les géométries sur les quatre
cartes réussies, avec environ 5 à 9 % de temps en moins sur des mesures uniques.
`azukar_fpga` échoue et restaure la carte avant comme après : ce n'est pas une
validation fonctionnelle réussie. Le rapport initial PACK0 signalait une
régression de connectivité sur le net 11 ; ne pas attribuer sans diagnostic
tout nouvel échec à cette même cause.

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
