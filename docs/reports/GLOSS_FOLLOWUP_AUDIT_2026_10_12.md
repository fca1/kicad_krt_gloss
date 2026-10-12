# Gloss : nouvelle passe après les commits de performance

## État vérifié

La série demandée est déjà enregistrée dans Git : `a4a10bd` (améliorations
géométriques), `44c6c16` (recherches et graphe), `8121a1d` (grille différée et
cache des pads), puis `4bd0eb8` (zones et contacts du même net). Aucun changement
du moteur ne restait à commiter au début de cette passe. Le fichier non suivi
`KRT/~test_board.kicad_pcb.lck`, préexistant, reste exclu des commits.

Cette passe analyse `4bd0eb8`. Les expériences décrites ci-dessous sont des
prototypes externes au dépôt, chargés seulement dans leurs processus de mesure.
Le moteur livré et les sources KRT ne sont pas modifiés. KRT reste à
`9577628635e3de81d2c1fd8ac882254c0fa7d032`.

## Vérifications et petite variation temporelle

Les 361 tests ciblés passent de nouveau, en 1,44 s. Les nouveaux profils de
tildagon_base et azukar_fpga retrouvent exactement les signatures géométriques
de la campagne précédente, avec G5 valide et sans expiration du budget.

La hausse précédente de 1,5 % sur chart_plotter_hat avec corridor n'est pas
reproduite de façon stable. Cinq nouvelles paires, avec ordre avant/après
alterné, donnent une médiane de 3,7072 s pour `8121a1d` et 3,6909 s pour
`4bd0eb8`, soit une baisse de 0,44 %. Les dix géométries et statistiques hors
chronométrage sont identiques. Selon la paire, la variation va d'environ
−3,1 % à +12,7 % de réduction : il y a de la dispersion, dont un essai de
référence à 4,2375 s. Ces mesures n'établissent ni un ralentissement systématique,
ni une accélération significative sur cette carte. Le bilan précédent reste
une observation historique valide ; il ne faut pas corriger du code sur le seul
symptôme d'un écart aussi petit.

## Coûts restants établis

Les durées ci-dessous sont instrumentées par cProfile, donc plus longues que
les exécutions normales. Les fonctions imbriquées ne doivent pas être additionnées.

| Fonction | tildagon_base, profil total 90,03 s | azukar_fpga, profil total 34,59 s |
|---|---:|---:|
| Clearance des segments (`early_segment`) | 29,15 s | 11,12 s |
| Connectivité locale, zones incluses | 20,96 s | 11,26 s |
| Contacts avec le cuivre du même net | 9,86 s | 1,52 s |
| Préparation/distance aux pads | 7,11 s | 5,43 s |
| Distance aux perçages étrangers | 4,34 s | 2,99 s |
| Tableaux KRT du cuivre étranger | 4,48 s | 0,92 s |

La présélection précédente a réduit le problème des petites zones sur azukar ;
les priorités ont changé. Les tableaux de cuivre représentent environ 5 % du
profil tildagon : leur seule optimisation ne peut pas fournir 20 % de gain total.

Un second diagnostic tildagon exécute tous les contrôles originaux, en observant
les répétitions exactes. Il conserve les objets pour éviter le recyclage de leurs
identifiants ; les nets avec zones incluent aussi le cuivre étranger dans la clé.

- 438 graphes de candidats sont recalculés comme références, pour 1,530 s ;
  deux autres répétitions candidat/candidat coûtent 0,0019 s.
- 19 541 contrôles de clearance répètent la même géométrie dans la même révision
  des listes de pistes et de vias, pour 0,597 s. Les décisions répétées sont
  comparées et identiques.
- L'exécution instrumentée prend 48,43 s. Ces coûts désignent du travail
  potentiellement évitable, pas un gain garanti : un cache a lui-même un coût
  et doit exclure les validations finales qui doivent rester fraîches.

## Expérience sur les tableaux de cuivre

Le prototype conserve les tableaux préparés entre recherches tant que les
listes de pistes et de vias sont les mêmes objets. Il n'active pas globalement
le drapeau privé KRT de confiance et n'intervient pas hors des recherches stables.
La revue des écritures actuelles retrouve les remplacements de listes dans
`GlossContext`, la restauration dans `transaction`, et les propositions KRT sur
copie dans `krt_merge`.

Sur tildagon_base, 2 447 préparations trouvent ainsi des tableaux réutilisables.
Mais l'essai complet mesure 46,274 s pour le moteur actuel et 46,516 s pour le
prototype, soit +0,52 % de temps. Géométrie et statistiques opérationnelles sont
identiques ; seuls les compteurs du cache changent, en plus des chronométrages.
Un essai ne permet pas d'établir une petite régression. Il ne démontre surtout
aucune accélération : cette piste n'est pas retenue comme priorité d'intégration.

## Expérience sur les pads polygonaux

Cause confirmée dans `clearance_preparation.prepared_pad_distance` : les pads
standards ont déjà une présélection physique, mais chaque pad polygonal étranger
est envoyé au calcul de distance, même loin du candidat. Sur azukar, le profil
compte 90 331 appels à `polygon_axis_distance`.

Le prototype prépare le rectangle de tous les sommets de chaque pad polygonal,
puis conserve le pad si ce rectangle peut atteindre le candidat avec sa
demi-largeur et la plus forte clearance applicable. La marge est arrondie vers
l'extérieur ; les données non finies ou sans sommets gardent le chemin complet.
Les pads retenus utilisent exactement la distance KRT actuelle. La présélection
ne privilégie aucune direction dans la décision exacte ; le nombre de voisins
retenus par les rectangles peut varier après rotation.

En mode de comparaison, chaque requête exécute les deux versions et le moteur
continue à utiliser la version originale. Les 30 889 décisions de clearance
sont identiques. 90 283 des 90 331 calculs polygonaux sont éloignés et peuvent
être écartés, soit 99,95 %. Trois essais par version, avec ordre alterné,
donnent une médiane de 15,624 à 14,705 s, soit **−5,88 %**, avec géométrie,
statistiques hors chronométrage et G5 conservés. Les réductions par paire
sont de 7,46 %, 3,12 % et 10,10 %. Les mesures individuelles sont enregistrées
dans les données associées.

Un contrôle sur complete1 retrouve la signature exacte, les 14,7240 mm gagnés,
G5 et les statistiques opérationnelles. Il ne rencontre aucun calcul de pad
polygonal dans ce chemin : ses 4,239 contre 4,165 s illustrent la variation de
mesure et ne prouvent pas un gain de cette optimisation sur complete1.

Ce prototype change les distances intermédiaires des obstacles hors de portée,
pas la décision au seuil physique. Il ne faut donc pas exiger l'égalité de toutes
les distances numériques, ni présenter cette validation comme une preuve
universelle. Une intégration doit ajouter les cas limites : polygones multiples,
pad décentré, clearance locale et de classe, rotation, contact au seuil,
coordonnées extrêmes, puis comparer les cinq cartes PACK0 avec et sans corridor.

## Priorités proposées

1. Présélection des pads polygonaux : coût confirmé et gain observé dans un
   prototype qui conserve les décisions. C'est le prochain changement le plus
   concret, sous réserve de sa validation ciblée et du corpus complet.
2. Préparer les perçages fixes et présélectionner leurs capsules avec toutes les
   règles de clearance. Le profil confirme un coût, mais aucun gain de cette
   proposition n'a été mesuré dans cette passe. KRT doit garder le calcul exact,
   les trous oblongs et les perçages dépassant leur anneau de cuivre.
3. Réutiliser un grade électrique accepté seulement après un commit correspondant
   exactement à son cuivre et à ses dépendances de zones. Le potentiel observé
   est modeste ; la complexité des invalidations impose de le traiter après les
   présélections géométriques. G5 reste recalculé.

L'élargissement général du cache de clearance est moins prioritaire : les
19 541 doublons observés coûtent seulement 0,60 s. La réutilisation supplémentaire
des tableaux de cuivre n'a pas montré de gain. Aucune de ces expériences ne
démontre encore une nouvelle baisse globale supérieure à 20 %. Les gains ne
doivent ni être extrapolés aux autres cartes, ni être additionnés entre profils.

## Protocole, données et limites

Les [données de cette passe](data/gloss_followup_audit_2026_10_12.json) conservent
les mesures individuelles, empreintes, compteurs et comparaisons. Les processus
sont neufs et séquentiels. Budget de 600 s pour éviter de comparer des recherches
interrompues ; vias mobiles et une passe G4. Parsing et écriture sont exclus du
temps moteur. Les règles et entrées sont celles de la campagne précédente ;
leurs empreintes sont vérifiées et les sources PCB restent intactes.

Traces externes dans
`C:/Users/frant/Downloads/cube_pcb1/comparaison_gloss_20261012/` :
`review_4bd0eb8_profile.py`, profils des deux grandes cartes,
`review_4bd0eb8_compare.py`, `review_4bd0eb8_chart_pairs.jsonl`,
`review_4bd0eb8_audit.py`, `review_4bd0eb8_duplicates.jsonl`,
`review_4bd0eb8_array_prototype.py`, `review_4bd0eb8_array_prototype.jsonl`,
`review_4bd0eb8_custom_prototype.py`, `review_4bd0eb8_custom_prototype.jsonl`.

Cette passe ne refait pas un DRC natif complet, la sérialisation des sorties,
ni la qualification Linux/macOS. Le xfail adversarial KRT connu reste une limite.
Les résultats des prototypes ne constituent pas une intégration du moteur.
Aucun plugin installé, ZIP créé ou fichier KRT modifié.
