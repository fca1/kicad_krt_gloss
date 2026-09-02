# Track Gloss — API Python d'intégration KRT

Ce document définit le contrat de l'entrée Python que KRT peut appeler
directement. Cette API doit rester indépendante du plugin, de `pcbnew` et de la
présentation KiCad.

## Finalité de l'API

`run_post_smooth_gloss()` permet à KRT de transmettre son état de routage déjà
construit à dgloss sans conversion vers une API graphique et sans nouveau
smooth implicite.

Son premier emploi est l'appel unique situé après le dernier smooth KRT. Elle
doit néanmoins rester publique et compatible avec les structures KRT afin de
permettre, à terme, que le gloss soit utilisé comme `smooth`, participe au
processus d'autoroutage ou soit déclenché à un autre point choisi par KRT.

KRT reste propriétaire du moment de l'appel. Dgloss reste propriétaire de ses
algorithmes et ne demande aucune modification du moteur KRT ou de son code
Rust.

## Contrat cible

L'entrée conserve les objets et conventions KRT :

```python
run_post_smooth_gloss(
    results,
    pcb_data,
    config,
    gloss_config=None,
    *,
    net_ids=None,
    krt_strips=None,
    krt_stats=None,
    krt_ms=0.0,
)
```

`net_ids` est optionnel afin de préserver la compatibilité des appels existants.
Il est pris en charge par le dépôt autonome `kicad_krt_gloss`.

## Paramètres

| Paramètre | Origine | Rôle |
|---|---|---|
| `results` | KRT | Liste de résultats à compléter selon les conventions KRT |
| `pcb_data` | KRT | État complet du PCB au moment choisi par l'appelant |
| `config` | KRT | `GridRouteConfig`, comprenant notamment le vrai `grid_step` de l'appel |
| `gloss_config` | dgloss | Options propres au gloss ; valeurs par défaut si absent |
| `net_ids` | KRT ou plugin | Nets complets à traiter ; `None` ou liste vide signifie tous les nets |
| `krt_strips` | KRT | Segments déjà remplacés par le traitement précédent |
| `krt_stats` | KRT | Statistiques du traitement KRT précédent |
| `krt_ms` | KRT | Temps KRT à conserver séparément du temps dgloss |

La sélection porte sur les nets complets. Les objets éventuellement
sélectionnés dans une interface servent uniquement à construire `net_ids` ; ils
ne limitent pas la portée géométrique à une sous-connexion.

`GlossConfig.enable_multipasses`, actif par défaut, demande à G4 de rappeler la
chaîne G3.5 complète pour chaque net selon un ordre alterné. Chaque rappel
interne force cette option à `False`, de sorte que seul l'orchestrateur G4 crée
les passes. `enable_noncollinear_t_rails`, également actif par défaut, contrôle
la variante correspondante de G3.3.

## Grille

Lors d'un appel direct par KRT, `config.grid_step` est obligatoire et représente
la résolution réellement utilisée par KRT. Dgloss ne lui substitue ni la grille
courante d'une interface, ni une valeur inférée depuis le cuivre, ni une
recherche au micron.

Le défaut de `0,1 mm` concerne uniquement un appel autonome qui ne dispose pas
d'une configuration KRT antérieure. Il ne doit jamais remplacer une valeur
effective fournie par KRT.

## Préconditions

- `pcb_data` décrit un état complet et cohérent du routage.
- `config` est compatible avec cet état et contient les règles nécessaires à
  la reconstruction des obstacles.
- L'appelant ne modifie pas simultanément les objets transmis.
- Si l'appel intervient ailleurs qu'après le dernier smooth, KRT assume
  explicitement l'ordonnancement et l'utilisation ultérieure du résultat.

## Résultat et propriété des données

L'appel renvoie un `GlossOutcome` contenant les objets KRT à retirer, les
changements structurés et les statistiques. Il peut compléter `results` et
mettre à jour `pcb_data` selon le même modèle d'intégration que les traitements
KRT existants.

Une erreur dgloss restaure l'état reçu à l'entrée de l'appel. Aucune fonction
de cette API ne crée de couche User et aucune ne dépend de `pcbnew`.

Le résultat `stats` contient la certification finale G5 : validité, nombres de
segments et vias contrôlés, réémissions géométriquement conservées et temps de
certification. G5 ne modifie pas le routage reçu de G4.

## Compatibilité à préserver

- Conserver `run_post_smooth_gloss` dans `dgloss.__all__`.
- Employer les types KRT plutôt que des copies propres à dgloss.
- Ajouter les nouveaux paramètres en options nommées avec des défauts
  rétrocompatibles.
- Ne jamais imposer le plugin pour utiliser l'API.
- Ne jamais imposer un CLI pour utiliser l'API.
- Tester l'import et l'exécution sans `pcbnew`.
