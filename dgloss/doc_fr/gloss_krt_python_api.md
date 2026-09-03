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
    excluded_net_ids=None,
    krt_smooth_complete=False,
    seed_segments=None,
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
| `excluded_net_ids` | appelant | Exclusions supplémentaires imposées par le support d'entrée, notamment les arcs natifs |
| `krt_smooth_complete` | KRT | Certifie que le dernier smooth est déjà terminé |
| `seed_segments` | KRT ou plugin | Instances `Segment` finales servant de graines à une portée par branches élémentaires |

Sans `seed_segments`, la sélection porte sur les nets complets. Avec des
graines, G0 résout une seule fois l'union de leurs branches élémentaires et
toutes les étapes restent dans cette portée. Les graines doivent être les
instances présentes dans le `pcb_data` transmis après le smooth ; elles ne sont
pas des copies géométriques. Le reste de chaque net demeure présent comme
cuivre fixe pour les obstacles, la topologie et la certification finale.

G0 fusionne cette portée avec les protections KRT : groupes à longueur ou temps
imposé, paires différentielles couplées, impédance et cuivre verrouillé. Les
arcs reconnus dans les données KRT ou signalés par `excluded_net_ids` sont aussi
exclus. Une exclusion concerne toujours le net complet et n'est pas levée par
une sélection explicite.

`GlossConfig.enable_multipasses`, actif par défaut, demande à G4 de rappeler la
chaîne G3.5 complète selon un ordre de nets alterné. Chaque passe complète
appelle une seule fois le noyau privé G3.5 avec toute la liste ordonnée ; il
n'existe plus de rappel autonome par net. Toutes les passes réutilisent le
contexte, la grille et la base d'obstacles construits une fois par G0. L'entrée
publique `run_post_smooth_gloss()` n'est appelée qu'une fois. L'option
`enable_noncollinear_t_rails`, également active par défaut, contrôle la variante
correspondante de G3.3.

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
- Conserver `seed_segments=None` comme comportement historique sur nets
  complets.
- Ne jamais imposer le plugin pour utiliser l'API.
- Ne jamais imposer un CLI pour utiliser l'API.
- Tester l'import et l'exécution sans `pcbnew`.
