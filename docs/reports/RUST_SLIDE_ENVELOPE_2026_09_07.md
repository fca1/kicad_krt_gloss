# Enveloppe de glissement décalée et marges Rust

Essai du 7 septembre 2026, demandé après l'analyse du prototype adaptatif.
Les réponses de la grille sont observées, sans modifier l'acceptation exacte
des candidats. Aucun changement de production ou de KRT.

## Paramètres et point des 0,3 mm

L'échange « Tester les marges KRT à zéro » a été relu. Il portait sur le
transfert d'une clearance de 0,3 mm incorporée à la carte vers un rayon de
contrôle : trois cellules pour une grille de 0,1 mm, ou 0,6 mm de largeur
supplémentaire. Ces 0,3 mm ne doivent ni être confondus avec le pas de grille,
ni ajoutés une seconde fois à une carte qui les incorpore déjà.

L'essai présent utilise les paramètres réellement construits par KRT :

| Carte | Pas | Clearance de configuration | Largeur réservée par couche |
|---|---:|---:|---:|
| bitaxe_ultra | 0,1 mm | 0,1524 mm | 0,254 mm |
| picofx_pump | 0,1 mm | 0,2 mm | 0,254 mm |

Les marges passent par `track_margins_for_width`, qui tient compte de la
réserve et des corrections de discrétisation de KRT. Pas de compensation
constante supplémentaire de 0,3 mm, pas de reconstruction à clearance zéro.

Le comportement spécial de `segment_blocked(r=0)` est reproduit dans un test :
seule l'arrivée est vérifiée. Les sondes emploient `_segment_fits_wide`, dont
le chemin à marge zéro parcourt la ligne complète. Les marges positives passent
par le test de capsule Rust. Les sources et le binaire KRT restent inchangés.

## Trois enveloppes comparées

- **Initiale** : segment au début de l'intervalle, rayon supplémentaire égal
  au déplacement maximal de ses extrémités.
- **Centrée** : segment au milieu de l'intervalle, moitié de ce rayon.
- **Centrée avec garde d'arrondi** : même enveloppe, largeur augmentée de
  `sqrt(2) * grid_step`, couvrant le déplacement maximal des extrémités lors
  de leur arrondi sur la grille. Cette garde n'est pas une preuve générale
  d'équivalence entre la grille et les règles géométriques.

Le rayon couvre le déplacement normal ET tangentiel des extrémités : le
segment central peut changer de longueur. Les variantes sont comparées au
verdict exact de l'enveloppe centrée actuelle ; elles couvrent toutes le
balayage, mais ne sont pas des formes identiques.

Les cartes excluant le net, les marges calculées et les réponses identiques
sur cellules/marge sont réutilisées. Chaque variante a son cache indépendant,
limité à une recherche ; l'ordre des variantes tourne entre les consultations.

## Résultats

Un seul passage instrumenté par carte, sans préchauffage. Budget porté à 120 s
pour ne pas tronquer la recherche à cause de l'observation. Aucun PCB écrit ;
empreintes source vérifiées. Les temps ci-dessous sont ceux des consultations,
pas un benchmark d'accélération globale de Gloss.

| Carte / enveloppe | Consultations | Temps grille | Réponses libres | Grille libre / exact refusé | Grille bloquée / exact accepté |
|---|---:|---:|---:|---:|---:|
| bitaxe / initiale | 8 681 | 23,4 ms | 56 | 0 | 3 990 |
| bitaxe / centrée | 8 681 | 23,5 ms | 119 | 0 | 3 927 |
| bitaxe / centrée + garde | 8 681 | 23,2 ms | 59 | 0 | 3 987 |
| picofx / initiale | 1 999 | 13,5 ms | 194 | 32 | 670 |
| picofx / centrée | 1 999 | 13,6 ms | 290 | 32 | 574 |
| picofx / centrée + garde | 1 999 | 13,4 ms | 135 | 0 | 697 |

Toutes ces enveloppes ont au moins une coordonnée hors grille. Les réponses
libres de la variante centrée représentent 1,37 % des consultations sur bitaxe
et 14,51 % sur picofx. Les consultations Rust effectives de cette variante sont
respectivement 1 007 et 983 ; les autres sont des réutilisations de cache.

Les contrôles exacts de référence des enveloppes centrales coûtent 2,176 s
sur bitaxe et 0,343 s sur picofx. Sur les seuls cas « grille libre », ils
représentent 33,1 ms et 59,8 ms. Même en supposant leur remplacement possible,
le gain brut après paiement des consultations grille serait seulement environ
10 ms et 46 ms, avant les autres frais. Ce remplacement n'est PAS validé :
32 réponses libres de picofx contredisent le certificat exact de l'enveloppe.

Avec la garde d'arrondi, ces désaccords disparaissent dans cet échantillon,
mais le coût grille dépasse déjà le temps exact des cas libres sur bitaxe
(23,2 ms contre 16,1 ms). Sur picofx, ces temps sont 13,4 ms contre 36,5 ms.
L'absence de désaccord observé avec la garde n'établit pas une garantie générale.

Les déplacements acceptés restent ceux du prototype exact :

| Carte | Gain | G5 | Connectivité | Arrêt |
|---|---:|---|---|---|
| bitaxe_ultra | 77,1097 mm | Valide | 0 régression | Convergence |
| picofx_pump | 96,6173 mm | Valide | 0 régression | Convergence |

Un refus de l'enveloppe exacte ne prouve pas que la trajectoire réelle heurte
un obstacle : l'enveloppe elle-même reste conservative. Les désaccords grille /
exact ne sont donc pas présentés comme 32 collisions de pistes démontrées.

## Conclusion de l'essai

Décaler l'enveloppe au milieu augmente les réponses libres, avec un coût Rust
faible. Mais cette voie, utilisée comme certificat rapide « libre », ne suffit
pas à récupérer les secondes perdues par le prototype. Elle laisse la plupart
des cas à l'exact et présente des désaccords hors grille. Un rejet automatique
sur « bloqué » sacrifierait de nombreux cas certifiables.

La grille peut encore orienter les tailles d'intervalle et l'ordre des essais,
sans se substituer à la validation. La limitation du travail par candidat et
la réutilisation des certificats des voisins restent prioritaires.

Validation : 18 tests spécifiques, couvrant rotations/réflexions, enveloppes,
cache, marge zéro et conversion 0,3 mm / rayon / largeur. Les comparaisons
complètes sur carte exercent aussi le harnais d'observation. Résultats locaux :
`.build/rust_envelope_bitaxe.json` et `.build/rust_envelope_picofx.json`.

```text
python tools/benchmark_rust_slide_envelope.py <carte.kicad_pcb> --output <resultat.json>
```
