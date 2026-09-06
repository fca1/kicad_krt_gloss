# Gloss : correctifs, temps réels et revue des algorithmes

Date : 6 septembre 2026. Branche `improve_gloss`, HEAD `798cc34`.
`Interpad...HEAD` : 0 commit manquant, 1 commit supplémentaire.
Les modifications de cette passe ne sont pas commitées.

## Résultat

La régression de temps est fortement réduite sur dispenser et picofx_pump.
Elle n'est pas entièrement résolue sur ember_he. La sécurité électrique locale
est renforcée, sans fixer les points de contact aux zones comme des ancrages
géométriques obligatoires.

| Carte | HEAD, comparaison précédente | Avant ces correctifs | Après, convergence | Gain avant → après |
| --- | ---: | ---: | ---: | ---: |
| dispenser | 10,93 s | 23,71 s | 7,92 s | 20,3142 → 20,3142 mm |
| picofx_pump | 17,14 s | 18,76 s | 14,91 s | 130,0515 → 130,2172 mm |
| ember_he | 17,96 s | 34,58 s | 24,80 s | 43,8247 → 43,3194 mm |

Ces temps sont des mesures murales parse + configuration + gloss, sans
profileur, pas des médianes statistiques. Les mesures HEAD et « avant » viennent
de l'A/B précédent, avec les mêmes fichiers et la même dépendance KRT.
Budget de recherche 60 s, grille 0,1 mm, tous les nets routés demandés,
exclusions de protection conservées, `stay_in_corridor=false`.
Les trois sorties corrigées convergent et passent la certification KRT finale.

Attention : ember_he reste plus lent que HEAD et son gain baisse de 0,5053 mm
par rapport au code précédent, de 0,2529 mm par rapport à HEAD. Les certificats
locaux modifient le choix et l'ordre des candidats. Cela ne démontre pas que
tout ce gain perdu correspondait à du cuivre invalide : la sélection reste
heuristique, pas une optimisation globale de la carte.

## Correctifs réalisés

1. Un certificat électrique local compare les identités des groupes de pads
   et zones, à partir du graphe KRT. Un nombre identique de composants ne suffit
   plus à masquer un échange de connexions. Les validations locales, de passe
   et finale utilisent la même définition de partition.
2. Les recherches de raccourcis, approches de pads, jonctions et vias essaient
   les autres candidats lorsqu'un candidat échoue électriquement. Les
   combinaisons de raccourcis sont aussi contrôlées : deux retraits de contacts
   redondants peuvent être inoffensifs séparément, mais dangereux ensemble.
3. Le filtrage grille KRT revient avant les coûteux contrôles géométriques
   dans les familles nombreuses de chamfreins. Les sondes canoniques et les
   propositions adaptatives conservent leur recours géométrique. Le cuivre
   conservé bénéficie de l'exception existante de réutilisation de segment.
4. Les distances KRT aux pads fixes sont mémorisées par coordonnées exactes,
   net, couche et clearance effective, dans un cache LRU de 8192 entrées.
   Il appartient à un seul adaptateur/une seule exécution. Les distances aux
   pistes et vias mobiles ne sont jamais mémorisées par ce cache.
5. Les certificats du même candidat ne sont plus recalculés après sa sélection.
   Le certificat initial est construit à la demande. Une position de via moins
   bonne que la meilleure déjà certifiée n'est plus vérifiée inutilement.
6. Un banc de mesure en lecture seule, `tools/benchmark_gloss.py`, expose
   hashes d'entrée, temps, étapes, passes, cache et convergence ; `--profile`
   ajoute un profil de coût. Les tests historiques dépendant de l'ancien
   prétraitement ont été adaptés au pilote partagé déjà introduit.

## Où se perd encore le temps ?

### Mesures finales, sans profileur

| Opération cumulée | dispenser | picofx_pump | ember_he |
| --- | ---: | ---: | ---: |
| Recherche de raccourcis/glissements de pistes | 5,65 s | 12,74 s | 14,80 s |
| Approches de pads | 0,52 s | 0,31 s | 1,83 s |
| Jonctions | 0,19 s | 0,22 s | 2,01 s |
| Vias locaux + chaînes longues | 0,26 s | 0,40 s | 2,71 s |
| Simplification à longueur égale | 0,23 s | 0,36 s | 1,25 s |
| Certification finale | 0,030 s | 0,050 s | 0,111 s |

Les temps d'opérations ne comprennent pas tous les frais de préparation,
mise à jour des obstacles et validation de passe. Les cumuls de fonctions
imbriquées d'un profileur ne doivent pas être additionnés.

Le profil intermédiaire de dispenser attribuait 15,17 s cumulées sur 23,61 s
profilées aux distances de pads, dont 13,76 s aux pads personnalisés : motivation
directe du cache. Le run final obtient 6516 hits pour 3762 misses.

Sur ember_he, après le cache de pads, le profil intermédiaire montre notamment
16,61 s cumulées de connectivité, 14,51 s de recherche de glissements,
4,44 s de préparation/vérification des tableaux de cuivre KRT, et 4,36 s dans
`ZoneFillModel.largest_component`. Ces chiffres précèdent la suppression des
certificats locaux en double ; ce ne sont pas les temps muraux finaux.
Le cache de pads final obtient 18412 hits pour 10642 misses.

### Passes tardives

- dispenser : 1,315 s pour 2,2901 mm ; 0,990 s pour 0,4971 mm ;
  0,772 s pour 0,2485 mm ; 0,815 s pour confirmer zéro gain.
- picofx_pump : 2,480 s pour 22,0412 mm ; 1,985 s pour 4,4735 mm ;
  1,645 s pour 3,0083 mm ; 1,586 s pour 1,9882 mm ; 1,609 s pour zéro gain.
- ember_he : 4,863 s pour 4,9874 mm ; 4,176 s pour 0,1657 mm ;
  4,099 s pour confirmer zéro gain.

L'enjeu suivant est donc de ne pas refaire une recherche complète dans les
régions inchangées. Il ne faut pas simplement exclure les nets inchangés : une
modification de cuivre étranger peut débloquer un candidat précédemment refusé.

## Budget interactif et contrôle réel

Avec 20 s de budget :

| Carte | Temps mural | Gain | Arrêt |
| --- | ---: | ---: | --- |
| dispenser | 8,01 s | 20,3142 mm | convergence |
| picofx_pump | 14,97 s | 130,2172 mm | convergence |
| ember_he | 20,43 s | 43,3194 mm | budget, convergence non certifiée |
| bitaxe_ultra complète | 20,36 s | 115,2939 mm | budget, convergence non certifiée |

Les quatre résultats passent la certification KRT finale. Le budget est une
limite souple de recherche : une vérification en cours et les certifications
finales se terminent. Ce n'est pas une garantie de réponse temps réel stricte.

Sur bitaxe_ultra, contrôle supplémentaire avec le Python natif de KiCad :
chargement, remplissage des zones, application en mémoire du delta, nouveau
remplissage puis graphe natif. Les 140 pads GND restent connectés en un seul
groupe, incluant C22/C23/C24/C25, après le gloss de GND seul puis après celui de
la carte complète. Delta complet testé : 466 pistes retirées, 320 ajoutées,
17 vias déplacés ; gain 115,2939 mm. Aucun fichier source enregistré.
Le sous-processus SWIG signale des objets de pistes non libérés à sa fermeture ;
ce banc natif ponctuel ne mesure pas les allocations du plugin.

Ce contrôle ciblé n'est pas un DRC natif exhaustif des quatre cartes. Les
modèles de remplissage KRT utilisés localement restent ceux chargés/cachés par
KRT ; une invalidation des zones dépendant de cuivre étranger modifié reste un
point à traiter avant toute garantie générale sur les remplissages futurs.

## Suite recommandée, dans l'ordre

1. **Réutilisation sûre des recherches** : versions de géométrie et invalidation
   par région touchée, commune aux différentes stratégies. Mesurer les taux
   de réutilisation avant d'introduire une planification plus compliquée.
2. **Mieux exploiter les données KRT** : réutiliser les tableaux de cuivre dans
   une révision de géométrie garantie stable ; éviter leurs scans de signature
   à chaque segment. Ne jamais contourner leur invalidation sur un déplacement.
3. **Modèles de zones** : mémoriser le plus grand composant pour un modèle
   immuable et identifier les zones affectées avant de reconstruire les modèles.
   Préférer une API KRT explicite à un cache parallèle supposé toujours valide.
4. **Recherche de glissements** : conserver l'arrêt au premier obstacle confirmé,
   mais chercher des réutilisations de certificats et du filtrage grille. Ne pas
   remplacer une validation du chemin balayé par le seul test de son extrémité.
5. **Interaction** : si un retour inférieur à la seconde est requis, il faudra
   une recherche interruptible/reprenable avec certification transactionnelle.
   Une limite de 20 s et un cache ne suffisent pas à en faire du temps réel strict.

Pas de nouveau paramètre utilisateur pour le cache. Garder `grid_step` comme
paramètre de précision géométrique, pas comme accélérateur aveugle : il affecte
aussi les longueurs minimales et les gains acceptés. `stay_in_corridor` demeure
un choix de comportement, pas un réglage de performance. Les anciennes étiquettes
d'étapes servent ici uniquement à mesurer, pas à imposer des frontières logicielles.

## Reproduction et entrées

Exemple PowerShell, depuis le dépôt :

```powershell
python tools/benchmark_gloss.py "C:\Users\frant\Documents\kicad_track_gloss_stress\sources\set21\ember_he.kicad_pcb" --budget 60
python tools/benchmark_gloss.py "C:\Users\frant\Documents\kicad_track_gloss_stress\sources\set21\ember_he.kicad_pcb" --budget 180 --profile
```

Ne pas comparer le temps d'un run profilé à celui d'un run normal.
Ne pas mélanger ces résultats avec les anciens scores d'un autre algorithme
ou avec une longueur de cuivre incluant les vias.

- dispenser : `Documents/KiCad/10.0/projects/dispenser/dispenser.kicad_pcb`
  SHA256 `2b5ae5932e9823558456684c43a00cb78bf99458f843e54fa5760040aba729a0`.
- picofx_pump : `Documents/kicad_track_gloss_stress/sources/set21/picofx_pump.kicad_pcb`
  SHA256 `d4859e08476fe28504782f41ace60e3e16802430394b8e1dceb76de55e538328`.
- ember_he : `Documents/kicad_track_gloss_stress/sources/set21/ember_he.kicad_pcb`
  SHA256 `59230b11c95ef87060f98004478200a86e4583ed7dc57387288bfb7d6a3be078`.
- bitaxe_ultra : `Documents/kicad_track_gloss_stress/sources/set1/bitaxe_ultra.kicad_pcb`
  SHA256 `267a1aa4475efa098e13af90b2f5280f69b5e9ed2fc7f71da87dccb56a8adec9`.
