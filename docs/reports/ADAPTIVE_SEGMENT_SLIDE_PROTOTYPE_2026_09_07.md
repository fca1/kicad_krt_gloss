# Prototype de glissement adaptatif — 7 septembre 2026

Prototype demandé après la revue des glissements. Il reste dans `tools`,
sans activation en production, option UI ou modification de KRT.

## Méthode

`tools/adaptive_segment_slide.py` calcule analytiquement la dérivée de la
longueur totale par rapport au déplacement normal du segment central. Avant
inversion des segments, cette longueur est affine. La recherche choisit le
seul sens décroissant ; une pente nulle ne déclenche aucun contrôle KRT.

Elle commence à un pas de grille, double le déplacement jusqu'à rencontrer
une limite, puis affine par dichotomie à une résolution de grille / 4.
Chaque déplacement doit prolonger un intervalle déjà certifié depuis la
position initiale. Une position finale libre derrière un obstacle ne suffit
jamais à accepter le déplacement.

Les voisins restent sur leurs supports fixes : leur union pendant le
déplacement est exactement leur état le plus long. Le segment central est
couvert par une capsule élargie au milieu de l'intervalle. KRT vérifie cette
enveloppe ; si elle est inconclusive, on subdivise. Une collision réelle au
milieu entraîne immédiatement le refus. La géométrie finale arrondie est
également vérifiée. Les données cuivre KRT sont réutilisées via `stable_copper`.

Limites de coût par recherche : 32 candidats, 512 contrôles élémentaires KRT,
10 niveaux de subdivision du certificat, et respect du budget temporel.
En cas d'interruption, seul le meilleur candidat entièrement certifié est rendu.

Le harnais remplace le parcours par pas de `_reachable_segment_slides`.
Pour la réduction locale, il conserve les raccourcis existants et ajoute ce
glissement partiel seulement après leur échec. La copie expérimentale de cette
politique est dans `tools/adaptive_slide_local.py` ; elle n'est pas une seconde
implémentation à maintenir en production.

## Validation ciblée

40 tests passent, dont 22 propres au prototype : huit rotations avec et sans
réflexion, glissement partiel manqué par l'algorithme actuel, obstacle mince
entre deux positions libres, pente nulle, limite de contrôles et interruption
du budget avec conservation du résultat déjà certifié.

Dans le cas manqué par la recherche actuelle, le trajet passe par
`(0,5), (3,2), (8,2), (12,6)`, avec un pad étranger en `(5,3.5)`.
Le prototype récupère le glissement partiel ; les validations utilisent KRT.

Sur un exemple libre instrumenté avec un prédicat de clearance simulé, les
contrôles élémentaires passent de 159 à 36, avec six candidats adaptatifs.
Ce comptage démontre la réduction du parcours ; son chronométrage n'est pas
une mesure de performance réelle de KRT.

## Cartes connues — version finale du prototype

Un seul essai par variante et par carte, sans préchauffage ni répétition.
Gloss complet avec corridor activé, sans Centering, budget 20 s. Parsing exclu
du temps, construction du contexte et G5 inclus. Aucun fichier PCB écrit.

| Carte | Variante | Temps | Gain de longueur | Segments finaux |
|---|---|---:|---:|---:|
| bitaxe_ultra | Actuelle | 9,212 s | 55,1363 mm | 813 |
| bitaxe_ultra | Adaptative | 13,066 s | 77,1097 mm | 807 |
| picofx_pump | Actuelle | 3,139 s | 56,8770 mm | 260 |
| picofx_pump | Adaptative | 4,402 s | 96,6173 mm | 258 |

Les quatre essais convergent, passent G5 et rapportent zéro régression de
connectivité. Les empreintes des cartes sources restent inchangées.

| Carte | Recherches | Pentes nulles | Candidats | Contrôles élémentaires | Limites de coût atteintes |
|---|---:|---:|---:|---:|---:|
| bitaxe_ultra | 715 | 221 | 1 360 | 26 749 | 41 |
| picofx_pump | 607 | 222 | 1 300 | 6 832 | 2 |

Le résultat géométrique s'améliore, mais le temps total augmente d'environ
42 % et 40 % sur ces mesures uniques. Il ne faut donc pas intégrer ce
prototype tel quel si la priorité est le temps réel. Les certificats près
des obstacles et les nombreuses recherches locales infructueuses restent
les principaux axes de travail. Les différences de gain modifient aussi les
passes suivantes : le delta de temps n'est pas un pur coût de la dichotomie.

Résultats locaux : `.build/adaptive_slide_bitaxe_ultra.json` et
`.build/adaptive_slide_picofx_pump.json`. Reproduction :

```text
python tools/benchmark_adaptive_slide.py <carte_connue.kicad_pcb> --corridor --output <resultat.json>
```

## Essai exploratoire antérieur

Une première version, avant le resserrement des enveloppes, a été essayée
sur dispenser sans corridor global : 7,754 s / 20,4292 mm pour l'actuelle,
11,929 s / 20,4093 mm pour le prototype. Les deux passent G5 et convergent.
Cette version gonflait également les voisins fixes et subdivisait même après
une collision réelle au milieu. Ce résultat a motivé la version finale.
Dispenser n'a pas été rejouée ; ce résultat ne mesure pas la version finale.
Trace : `.build/adaptive_slide_dispenser.json`.

## Portée des garanties

La dichotomie affine une limite conservatrice de la déformation choisie,
pas nécessairement le déplacement maximal physiquement possible. Les refus
de clearance approchée ou de connectivité peuvent interrompre la recherche
avant une autre solution admissible. La géométrie reste octolinéaire aux
positions émises et ne privilégie aucune direction.

Les limites existantes concernant les contacts intermédiaires aux zones et
le cuivre du même net ne sont pas levées. Le contrôle final de connectivité
ne constitue pas un graphe exhaustif à chaque instant. Aucun DRC natif KiCad
ni remplissage de zones n'a été réalisé. Aucun changement de production,
ZIP ou push n'est inclus dans ce prototype.
