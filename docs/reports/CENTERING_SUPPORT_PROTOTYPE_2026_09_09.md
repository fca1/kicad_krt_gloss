# Prototype Centering par supports — 9 septembre 2026

Statut : **prototype séparé, non intégré au plugin**. KRT et les constructeurs
de production ne sont pas modifiés. Aucun ZIP produit.

## Construction

`tools/prototype_centering_supports.py` remplace temporairement, dans son seul
processus de test, le constructeur multi-porte. Les autres constructeurs sont
désactivés pendant cet essai : un rejet ne revient pas au chemin défectueux.
Le pipeline conserve Gloss préparatoire avec corridor, Centering, puis G5.

Chaque segment garde sa direction orientée. Les portes imposent la position
du support de leur segment ; deux portes du même segment doivent imposer la
même droite. Les intersections des supports donnent les nouveaux sommets.
Les supports non contraints restent fixes. Les ancres terminales restent fixes.
Un segment retourné ou deux contraintes incompatibles sont refusés.
Il n'y a ni longueur prédéfinie de passage ni bande de contrôle.

Les sommets sont ensuite déplacés successivement. KRT vérifie les triangles
balayés par les deux segments incidents avec la largeur physique du cuivre.
Les contrôles de passage, clearance finale, connectivité et G5 restent actifs.

## Essai natif `/A`, Proxi 2,54 mm

Source : `C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb`.
SHA256 : `08b5d8efe0990e9753f111b680fd1d95cf6ddb78e82888aa09182422c8f797fb`.
KiCad 10.0.6, Python `D:/kicad/bin/python.exe`, budget 20 s.

| Mesure | Résultat |
| --- | --- |
| Portes centrées, vérifiées après application native en mémoire | 3 / 3 |
| U1.2–U1.3 | Y 93,070711 → 93,155 mm |
| U1.3–U1.4 et U1.5–U1.6, même support | Y 95,9 → 95,695 mm |
| Longueur totale `/A` | 85,3560 → 85,3560 mm |
| Segments de la chaîne | 13 → 13 |
| Remplacement natif | 7 → 7, différences User.1 |
| G5 | valide, 7 segments certifiés |
| Ordre des directions / ancres | conservés |
| Changement d'enroulement autour des centres des pads étrangers | 0 |

Une mesure de développement donne 95,532 ms pour le moteur complet, dont
15,761 ms pour Centering et 1,257 ms pour G5. Elle exclut chargement, import
initial et application native ; ce n'est pas une campagne de performance.
Gloss préparatoire ne change pas la géométrie sur ce fichier.

L'application s'effectue sur une carte chargée en mémoire ; une seconde
importation du cuivre vérifie les trois passages et la présence des segments
attendus. Aucun SaveBoard ni interaction avec l'éditeur. L'empreinte du fichier
source est vérifiée inchangée après l'essai.

## Défaut préexistant rencontré

Le premier essai remplaçait toute la chaîne. KRT rejetait son segment d'indice 2,
de (150,1 ; 96,468318) à (152,331682 ; 98,7), **inchangé et déjà refusé dans la
source**. Le prototype limite désormais le remplacement à l'intervalle affecté,
indices 6 à 12 inclus. Aucun contrôle sur le cuivre modifié n'a été désactivé.
Ce résultat ne constitue pas une certification DRC globale de la carte source.

## Tests et limites

23 tests ciblés réussis : 16 tests du prototype, 7 tests d'architecture.
Ils couvrent rotations/reflets, contraintes partagées, contradictions, ancres,
retournement, refus des supports parallèles et des entrées non octolinéaires,
rejet du balayage et expiration du délai. L'essai natif ci-dessus a aussi réussi.

Le prototype ne cherche pas encore les translations de supports voisins libres
si les supports fixes rendent la solution impossible. Les supports consécutifs
parallèles sont refusés explicitement. Le certificat de balayage KRT porte sur
les obstacles étrangers ; une certification générale des auto-contacts pendant
le mouvement reste à ajouter avant intégration. Les contrôles finaux existants
sur les autres branches du même net et la connectivité sont conservés.
L'enroulement autour des centres des pads est un audit indépendant du cas testé,
pas un remplacement de la clearance ni une preuve topologique générale.

Conclusion : le cas `/A` peut être centré sans le raccourci catastrophique et
sans nouveau coude, par conservation des supports. Cette expérience ne corrige
pas encore le plugin installé et ne vaut pas validation sur d'autres cartes.

Commande reproductible :

```powershell
& D:/kicad/bin/python.exe tools/prototype_centering_supports.py C:/Users/frant/Downloads/kicad_centering/test_centering1/test_centering2.kicad_pcb
```
