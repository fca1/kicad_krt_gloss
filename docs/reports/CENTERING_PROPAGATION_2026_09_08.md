# Centering : propager le glissement, pas reconstruire un coude

## Cause et correction

Sur `/A`, le constructeur local prolongeait un voisin diagonal dont KRT refusait
déjà le support initial au contact d'un pad. Sa jonction extérieure n'était
pourtant pas une ancre : elle pouvait glisser sur le segment précédent.
Le repli de `f41a1b6` ignorait ces supports existants et reconstruisait une chaîne
avec un raccord vertical–horizontal à 90°.

Le correctif propage la translation de la porte à un ensemble contigu de
supports existants. Les jonctions sont leurs intersections ; les deux rails
extérieurs restent fixes, leurs longueurs s'adaptent. Les ensembles sont essayés
du plus petit au plus grand, jusqu'aux ancres KRT et dans le budget partagé.
Les contrôles de périmètre, clearance, même net, connectivité et G5 demeurent.
Aucune marge artificielle, taille de chanfrein ni détection d'angle corrective
n'est ajoutée. Le repli arbitraire monoporte est supprimé.

Deuxième défaut : après le Gloss préparatoire d'une carte déjà centrée,
une proposition inchangée était rejetée et déclenchait cette reconstruction.
Une porte inchangée est désormais soumise aux mêmes validations puis comptée
séparément comme déjà centrée et certifiée, sans remplacement de cuivre.
Elle permet de conserver le Gloss préparatoire. Aucune transformation n'a lieu
après le Centering. Aucune porte admissible ou une expiration reste un rollback.

## Reproductions natives détachées

KiCad 10.0.6, Proxi 2,54 mm, net `/A`, budget 20 s. Source sauvegardée :
`test_centering2.kicad_pcb`, SHA-256
`2d6b4f23ebd79ec9aefd94e15cf3862be208619810e2370aa7225f5a6b2bcaa6`.
Le fichier source n'est jamais sauvegardé ; son empreinte est vérifiée.

| Entrée | Résultat | Temps moteur avec G5 (mesure unique) |
| --- | --- | --- |
| Fichier actuel avec le coude | Gloss conserve son raccord diagonal ; 1 porte déjà centrée certifiée ; 55,2753 → 54,4203 mm | 96,2 ms |
| Rejeu des coordonnées antérieures à partir de User.1, sur carte détachée | 1 porte recentrée ; 54,5943 → 54,6939 mm (+0,0996 au lieu de +0,6810 mm) | 82,6 ms |

Dans le rejeu, le rail vertical X=149,875033 se prolonge de Y=88,945533
à Y=89,115533 : +0,17 mm. Le diagonal est conservé, puis rejoint le passage
à Y=90,615 mm. La chaîne reste à cinq segments ; quatre sont remplacés.
Le rejeu n'est pas présenté comme le fichier original intégral : il remet
les coordonnées enregistrées de cette chaîne dans le contexte du PCB actuel.

`tools/reproduce_centering_native.py CHEMIN_PCB [--replay-before]` vérifie
G5, application native, centre exact, ancres, raccords, cinq segments et la
présence du diagonal dans User.1. Ce n'est pas un essai visuel dans l'éditeur.

## Tests et limites

442 tests réussis et le même échec historique
`test_a_later_gloss_completely_removes_a_longer_centering_path` (aucune porte).
34 tests supplémentaires couvrent rotation, réflexion, sens de parcours,
arrêt aux rails verrouillés, budget et transaction avec porte déjà centrée.
KRT inchangé. Pas de ZIP ni de nouvelle campagne PACK0 dans cette passe ciblée.

La propagation conserve les supports existants ; elle ne prétend pas trouver
tous les chemins possibles lorsque cette famille est bloquée. Le constructeur
multiporte historique reste distinct et n'est pas refondu par ce correctif.
