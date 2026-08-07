---
name: datasheets-json
description: >
  Convention de stockage et méthode de lecture des datasheets de composants
  électroniques du projet : fichiers JSON paginés dans data_sheets/, captures
  d'écran extraites dans data_sheets/<composant>_images/. À charger avant de
  chercher une caractéristique de composant (brochage, pinout, tension, courant,
  adresse I2C, condensateur de découplage, boîtier, Absolute Maximum Ratings),
  et pour savoir quand ouvrir une image plutôt que du texte.
---

# Datasheets du projet : format et méthode de lecture

## 1. Où sont les datasheets

Les datasheets NE SONT PAS des PDF à lire. Elles ont été pré-extraites dans le
dossier de travail, à la racine du projet :

```
data_sheets/
  lm555.json                 <- le texte, page par page
  lm555_images/              <- les captures extraites de ce PDF
    page3_img1.png
    page7_img2.png
  esp32-c3.json
  esp32-c3_images/
  ...
```

Règle : un fichier `<composant>.json` est toujours accompagné d'un dossier
`<composant>_images/` portant le même préfixe.

`data_sheets/` est en LECTURE SEULE pour tous les agents, sans exception. C'est
une source de vérité fournie par l'utilisateur : personne ne la modifie, ne la
complète, ni ne la réécrit. Un garde-fou refuse d'ailleurs toute écriture dans
ce dossier.

## 2. Format du JSON

Un tableau d'objets, un par page du PDF d'origine :

```json
[
  {
    "page": 1,
    "texte_markdown": "...contenu textuel de la page...",
    "images": ["data_sheets/lm555_images/page1_img1.png"]
  },
  { "page": 2, "texte_markdown": "...", "images": [] }
]
```

Points importants :

- Les chemins listés dans `images` sont **déjà relatifs à la racine du projet**.
  Utilise-les tels quels, ne les reconstruis pas, ne préfixe rien.
- `images` peut être une liste vide : la page n'a pas d'illustration extraite.
- Le champ `page` correspond à la pagination du PDF d'origine : cite-le dans ton
  rapport, ça permet à l'utilisateur de vérifier dans le PDF original.

## 3. Méthode de lecture efficace

Ne lis jamais un JSON de datasheet en entier page par page : ce sont des
documents de 40 à 400 pages, tu épuiserais ton contexte avant d'arriver à
l'information utile.

Procédure :

1. `list_dir` sur `data_sheets/` pour voir quels composants sont disponibles.
2. `grep_search` sur le fichier JSON pour localiser les sections utiles. Les
   mots-clés qui paient, en anglais (les datasheets le sont presque toujours) :
   `Pin Configuration`, `Pinout`, `Pin Description`, `Electrical
   Characteristics`, `Absolute Maximum Ratings`, `Recommended Operating`,
   `Typical Application`, `Package`, `Thermal`, `I2C Address`, `Ordering
   Information`.
3. `view_file` sur les plages de lignes trouvées, en LARGES portions (200 à 500
   lignes d'un coup). Multiplier les petites lectures coûte plus cher que lire
   large une seule fois.

## 4. Quand ouvrir une image

`view_file` sait afficher une image. Mais une image consomme beaucoup plus de
contexte qu'un paragraphe de texte : ce n'est pas gratuit.

Ouvre une image UNIQUEMENT si l'information est vitale et absente du texte :

- un schéma de brochage complexe (BGA, QFN dense) que le texte ne détaille pas ;
- un graphique dont dépend un choix de dimensionnement (courbe de chute de
  tension, dérating thermique, rendement) ;
- un dessin mécanique de boîtier dont tu as besoin des cotes.

N'ouvre pas : logos, en-têtes, schémas décoratifs, illustrations d'application
déjà décrites dans le texte, tableaux qui existent déjà en markdown dans
`texte_markdown`.

Avant d'ouvrir une image, lis le texte de la page qui la contient : neuf fois
sur dix, l'information y est déjà, et sous une forme plus fiable qu'une lecture
visuelle.

## 5. Ce qu'il faut systématiquement en extraire

Pour tout circuit intégré destiné à être câblé :

| Information | Pourquoi c'est critique |
|---|---|
| **Noms exacts des broches** | SKiDL connecte par nom (`u1['GND']`), pas par numéro. Un nom approximatif casse le netlist. |
| Tensions d'alimentation (min/typ/max) | dimensionnement du régulateur |
| Courant consommé (typ/max) | dimensionnement de l'alimentation et des pistes |
| Condensateurs de découplage recommandés | valeur ET position ; leur absence est le défaut n°1 en ERC |
| Adresse I2C par défaut et broches de sélection | conflits de bus |
| Absolute Maximum Ratings | limites à ne jamais approcher |
| Résistance thermique (RθJA) | dissipation |
| Référence exacte du boîtier | recherche d'empreinte KiCad |
| Broches à ne pas laisser flottantes (EN, RESET, CS, NC) | source classique d'instabilité |

## 6. Honnêteté sur ce qui n'a pas été trouvé

Si une information n'est pas dans la datasheet extraite, dis-le explicitement :
« non trouvé dans `data_sheets/lm555.json` ». N'invente jamais un numéro de
broche, une tension ou une adresse I2C : une valeur inventée traverse toute la
chaîne jusqu'au circuit imprimé fabriqué, et coûte un tour de prototypage.

Cite toujours ta source sous la forme `fichier.json, page N`.
