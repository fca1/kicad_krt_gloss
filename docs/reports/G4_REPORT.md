# Rapport historique — G4 — validation des passes multinet

G4 réemploie la chaîne G3.5 complète, net par net, sans ajouter d'algorithme
géométrique. `enable_multipasses` est actif par défaut. Les appels G3.5 internes
le forcent à `False`, partagent le budget global et reconstruisent leur contexte
depuis le résultat courant.

## Résultats

Grille de test : 0,1 mm. Toutes les options G3.1 à G3.4 ainsi que la variante
des T sans rail colinéaire sont actives.

| Carte | Nets | Gain G3.5 avant passes | Gain G4 | Gain dgloss total | Passes | Arrêt | Régression de connectivité |
|---|---:|---:|---:|---:|---:|---|---:|
| `dispenser` | 31 | 7,1655 mm | 1,0245 mm | 8,1900 mm | 2 | convergence | 0 |
| `picofx_pump` | 39 | 34,6524 mm | 5,7717 mm | 40,4241 mm | 2 | convergence | 0 |
| `ember_he` | 61 | 22,7559 mm | 3,1894 mm | 25,9453 mm | 1 complète + 1 partielle | budget | 0 |

Le journal public contient les lignes G3 à G3.5 de l'exécution initiale, une
ligne par passe G4, puis le bilan global. Les G3.5 internes restent silencieux
mais leurs statistiques structurées sont conservées. Lorsque G4 est actif,
seule User.1 représente l'écart entre l'entrée du gloss et le résultat final.
