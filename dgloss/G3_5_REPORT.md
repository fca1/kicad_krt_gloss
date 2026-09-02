# G3.5 — intégration complète et configuration

G3.5 coordonne et certifie les étapes cumulées du gloss final sans modifier
les algorithmes KRT ni le code Rust.

## Intégration

- `run_final_gloss()` reste l'adaptateur très mince du plugin : dernier smooth
  KRT, puis gloss final.
- `run_post_smooth_gloss()` est le point d'entrée séparé prévu pour un futur
  CLI. Il reçoit le résultat final KRT et ne relance jamais le smooth.
- La grille, les obstacles et les contrôles de clearance sont reconstruits par
  `build_gloss_context()` avec les primitives KRT existantes.

## Configuration

`GlossConfig` appartient à `dgloss`. Les quatre options G3.1 à G3.4 sont
indépendantes, activées par défaut et persistées par le plugin. G3 demeure le
socle obligatoire. Le budget global du gloss vaut 20 secondes par défaut.

## Certification et visibilité

- Une instance `GlossStats` réunit l'état, les transformations, le gain et le
  temps de chaque étape, puis le bilan G3.5 structuré.
- Le log reste succinct : une ligne par étape et une ligne globale.
- La validation finale refuse une augmentation de longueur, une régression de
  connectivité, du cuivre non octolinéaire ou un segment plus court que le pas
  réel de la grille KRT.
- Toute erreur restaure exactement le résultat du smooth KRT.
- User.1 à User.5 conservent les évolutions G3 à G3.4 ; User.6 montre le résultat
  cumulé certifié G3.5 sans dupliquer le cuivre produit.

## Validation ciblée, toutes options actives

| Carte | Gain smooth KRT | Gain dgloss G3.5 | Nets améliorés | Temps dgloss |
|---|---:|---:|---:|---:|
| dispenser | 13,0505 mm | 3,1792 mm | 7 | 5,084 s |
| picofx_pump | 56,4882 mm | 31,4930 mm | 15 | 7,419 s |
| ember_he | 16,0068 mm | 18,7151 mm | 10 | 18,433 s |

Les trois cartes terminent sans régression de connectivité et sous le budget
post-smooth de 20 secondes. Les tests ciblés couvrent aussi la désactivation
indépendante de chaque option, le budget nul, l'absence de second smooth dans
le point d'entrée post-smooth et la couche cumulée G3.5.
