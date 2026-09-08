# Réduction locale du gloss

Avec `stay_in_corridor=True`, G3 utilise le parcours local en un seul sens,
orienté depuis un pad lorsque possible. Avec `False`, les recherches existantes
s'exécutent d'abord ; une passe locale est ensuite exécutée après G3.5 dans
chaque passe de gloss. Les multipasses existantes restent configurables.

Le parcours examine deux puis trois segments, propose des raccordements
octolinéaires et des positions limites de glissement, puis recommence depuis
le début après une modification. Il accepte une réduction de longueur ou une
diminution du nombre de segments à longueur égale. Chaque mouvement reçoit
un contrôle de clearance, de corridor et de connectivité. Les ancres de la
chaîne et le périmètre éditable sont conservés. Le budget borne le parcours ;
les modifications déjà certifiées peuvent être retournées à son expiration.

Le certificat de corridor reste conservateur : il vérifie une déformation
particulière, pas toutes les déformations possibles. Le parcours ne recherche
pas les glissements partiels arrêtés par un obstacle. Il ne garantit donc pas
une longueur minimale.

Validation ciblée sur `test_centering2.kicad_pcb`, net `/C`, grille 0,1 mm :

- Corridor actif : 104,4542 → 98,6860 mm, environ 0,15 s.
- Corridor inactif : 104,4542 → 56,0598 mm, environ 0,40 s.

L'action Centering commence par une passe de gloss avec
`stay_in_corridor=True`, sur le même périmètre éditable. Le centering s'exécute
ensuite dans le budget restant et constitue la dernière transformation.
Seules la certification et la préparation de l'affichage suivent le centering.
Le nettoyage préalable est inclus dans la transaction et dans le delta final.
