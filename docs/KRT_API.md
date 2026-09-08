# Interface Gloss / KRT

Les imports KRT du moteur `dgloss`, de la CLI `gloss.py` et du plugin
passent par `dgloss/krt_api.py`. KRT reste inchangé et conserve l'autorité
pour la géométrie, les obstacles, les clearances et les validations.

La table `_EXPORTS` relie les noms utilisés par Gloss aux modules et symboles
KRT. La résolution est différée jusqu'au premier import du symbole, puis
mémorisée. Les fonctions et classes sont celles de KRT : aucun appel de
délégation, copie ou conversion supplémentaire dans les boucles de calcul.
Les dépendances facultatives de placement et d'interface graphique ne sont
chargées que lorsqu'elles sont demandées.

Si KRT renomme ou déplace une fonction, adapter cette table. Si sa signature
change, ajouter ici une fonction d'adaptation explicite conservant le contrat
attendu par Gloss. Redémarrer le processus après une évolution de KRT : les
références déjà importées ne sont pas remplacées à chaud.

Cette façade centralise les imports, mais ne crée pas un modèle de données
indépendant de KRT. Une modification de ses objets peut donc nécessiter une
adaptation plus large. Les deux adaptateurs spécialisés existants conservent
leurs responsabilités : `krt_clearance.py` compose les validations KRT et
`zone_models.py` adapte les caches de zones, dont certains détails sont privés.
Ce dernier accède au module de zones via la façade.

La revue corridor du 8 septembre ajoute `krt_sweep` (composition continue des
formes et primitives KRT, sans échantillonnage des pads) et `krt_merge`
(propositions de fusion sur copie, contrôlées avant publication). Les tolérances
de calcul utilisent `FP_EPS_MM`, pas une fraction de grille ni une largeur de
contrôle. Les modèles et règles KRT restent inchangés.

Le démarrage de KRT et la vérification de ses dépendances restent dans
`kicad_krt_gloss/runtime.py`, avant l'utilisation de l'API. Les outils de test
et de benchmark peuvent importer KRT directement pour servir de référence.
Le module est inclus par la copie du répertoire `dgloss` lors du packaging.

Validation du 7 septembre 2026 : 78 tests ciblés réussis, couvrant la frontière
d'import, la résolution différée, l'identité des objets, les microsegments,
le corridor, les glissements, le prototype de déplacement, les règles Gloss,
la transaction Centering et les frontières du plugin. Démarrage CLI vérifié
avec `python gloss.py --help`. Pas de nouvelle mesure de performance sur carte
ni de test interactif dans KiCad pour cette modification.
