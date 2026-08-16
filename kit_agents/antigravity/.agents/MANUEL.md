# Manuel du dispositif multi-agents

Trois familles d'agents, une par domaine. Elles partagent le même protocole mais
ne se mélangent jamais.

---

# Comment ça marche, en une page

## Le principe

Chaque agent est une **conversation séparée et étanche**. Un sous-agent invoqué
démarre avec un contexte vierge : il n'a pas vu ta conversation avec
l'orchestrateur. Les agents ne se parlent donc pas directement, ils communiquent
par **fichiers déposés sur le disque** dans `.agent_reports/`.

Conséquences pratiques :

- Un agent qui a compris quelque chose doit l'ÉCRIRE pour que le suivant en
  profite.
- L'orchestrateur recopie dans chaque délégation les chemins et symboles qu'il a
  trouvés, sinon le sous-agent refait la recherche.
- Chaque rapport porte un identifiant de mission, sinon impossible de savoir s'il
  concerne le travail en cours ou celui d'il y a trois jours.

## Ce que tu fais, toi

1. Tu choisis l'agent principal correspondant au domaine (`code-orchestrateur`,
   `hw-orchestrateur` ou `meca-orchestrateur`).
2. Tu formules ta demande en français (expression libre, bug report, CDC complet),
   ou tu tapes la commande slash du workflow.
3. L'agent transversal **`spec-translator`** (PreWorkflow Step 0) transforme
   automatiquement ta demande en spécification technique anglaise normée
   (`.agent_reports/spec_ingress.md`), résout l'historique récent et mappe les
   vrais fichiers du projet.
4. Tu restes dans cette conversation. C'est l'orchestrateur qui invoque les
   spécialistes ; tu ne changes pas d'agent en cours de route.

Tu ne changes d'agent principal que pour zapper volontairement l'orchestrateur, sur
une tâche courte et isolée.

## Les cinq verdicts

Les agents terminent par un token exact, sur lequel l'orchestrateur route :

| Token | Signification |
|---|---|
| `APPROUVE` | La revue est passée, on continue. |
| `CORRECTIONS_REQUISES` | Rapport écrit, retour au concepteur ou au codeur. |
| `BLOQUE` | Impossible d'aboutir, la raison est dans la réponse. |
| `VALIDATION_VISUELLE_REQUISE` | Un humain doit regarder le rendu. |
| `RIEN_A_SIGNALER` | Audit fait, aucune anomalie réelle. C'est un bon résultat. |

## Les invariants communs aux trois modes

1. **Un seul routeur** : seul l'orchestrateur délègue. Un spécialiste qui a besoin
   d'un autre rôle termine par `BLOQUE`.
2. **Boucle plafonnée à 2 tours**, puis remontée à l'utilisateur.
3. **Seul l'agent principal te pose des questions.** Les sous-agents ont un délai
   d'interaction court et leur question expirerait.
4. **Jamais deux agents d'écriture en parallèle.**
5. **Jamais d'invention d'une valeur physique** : broche, tension, cote, propriété
   de matériau. Toute valeur manquante est isolée dans `Assumptions & Open Questions`
   de la spécification d'entrée et validée avant exécution.
6. **Passerelle linguistique étanche** : Toute consigne métier est traduite en
   anglais d'ingénierie normé avant transmission aux spécialistes.

---

# Mode CODE

**Agent principal : `code-orchestrateur`**

## Workflows

| Commande | Enchaînement |
|---|---|
| `/code-feature` | architect → coder → reviewer → test-writer → consistency-checker |
| `/code-bugfix` | debugger → coder → test-writer → reviewer |
| `/code-audit` | analyst + tech-lead en parallèle, security si le projet est exposé |
| `/code-retrocompat` | consistency-checker → coder → reviewer |

## Les 10 spécialistes (+ l'orchestrateur)

| Agent | Écrit | Rapport |
|---|---|---|
| `code-architect` | non | `code-architect.md` |
| `code-coder` | **le code** | non |
| `code-test-writer` | les tests seulement | non |
| `code-reviewer` | non | `code-reviewer.md` |
| `code-debugger` | non | `code-debugger.md` |
| `code-analyst` | non | `code-analyst.md` |
| `code-consistency-checker` | non | `code-consistency-checker.md` |
| `code-security` | non | `code-security.md` |
| `code-tech-lead` | non | `code-tech-lead.md` |
| `code-documentalist` | doc et docstrings | non |

## Utilisables en direct

`code-coder` (modification ciblée), `code-analyst` (comprendre du code),
`code-documentalist` (doc seule).

## Le graphe de code (optionnel mais recommandé)

Si tu fais tourner Graphify sur le projet, tu obtiens `graphify-out/` à la racine.
Les agents du mode code l'exploitent automatiquement :

| Agent | Ce que le graphe lui apporte |
|---|---|
| `code-orchestrateur` | il ne peut pas lire le code, mais il lit `GRAPH_REPORT.md` : enfin une carte pour router |
| `code-analyst` | la structure du projet en une lecture au lieu de dizaines |
| `code-consistency-checker` | `callers` liste les dépendants réels, y compris ceux qu'un grep rate |
| `code-coder` | avant de changer une signature, la liste exacte des appelants |
| `code-reviewer` | confronte les appelants du graphe au diff pour repérer un oubli |
| `code-debugger` | remonte la chaîne d'appel sans ouvrir dix fichiers |

Les requêtes passent par un script, jamais par une lecture directe de
`graph.json` (plusieurs mégaoctets écraseraient le contexte de l'agent) :

```
python .agents/scripts/graph_query.py stats
python .agents/scripts/graph_query.py callers "valider_commande"
python .agents/scripts/graph_query.py path "api" "base_donnees"
python .agents/scripts/graph_query.py schema      # si un résultat semble vide à tort
```

**Trois garde-fous intégrés dans les prompts :**

1. Une relation `INFERRED` est une hypothèse, jamais une base d'action : l'agent la
   vérifie au `grep_search` avant de toucher au code.
2. Un graphe plus ancien que les dernières modifications n'est fiable que pour la
   cartographie générale, pas pour les signatures. L'agent vérifie sa date.
3. `graphify-out/` est en lecture seule, appliqué par le garde-fou.

Le graphe localise, le fichier confirme, les tests valident. Aucun agent ne
régénère le graphe tout seul : c'est long et coûteux, ça t'appartient.

Sans `graphify-out/`, tout fonctionne comme avant avec `grep_search`.

## À savoir

- Le `code-consistency-checker` sert après l'ajout d'un champ ou d'un paramètre :
  il traque les endroits qui l'ignorent encore, notamment la saisie manuelle et les
  fixtures. C'est le bug silencieux le plus fréquent.
- Le `code-test-writer` n'affaiblira jamais un test pour le faire passer : s'il
  trouve un vrai défaut, il s'arrête et demande le coder.

---

# Mode HARDWARE

**Agent principal : `hw-orchestrateur`**

## Prérequis : le dossier des datasheets

```
data_sheets/
  lm555.json               tableau de pages : [{page, texte_markdown, images}]
  lm555_images/            captures extraites du PDF
    page3_img1.png
  esp32-c3.json
  esp32-c3_images/
```

Les chemins d'images dans le JSON sont déjà relatifs à la racine : ils s'utilisent
tels quels.

**Un seul agent lit ce dossier : `hw-component`.** Tous les autres travaillent à
partir de son rapport. Ce n'est pas une lubie : une datasheet fait couramment 300
pages, et laisser chaque agent la relire épuiserait leur contexte avant qu'ils
produisent quoi que ce soit. Le dossier est protégé en écriture par le garde-fou.

Si un composant n'a pas son JSON, l'agent te le dira et s'arrêtera. Il n'inventera
pas de brochage.

## Workflows

| Commande | Usage |
|---|---|
| `/hw-carte` | conception complète d'une carte |
| `/hw-datasheet` | consulter les caractéristiques d'un composant, sans concevoir |

## Le pipeline de `/hw-carte`

```
hw-architect          blocs fonctionnels, bilan de puissance, diagramme Mermaid
      ↓
hw-component          brochage exact depuis data_sheets/ (parallélisable)
      ↓
 [TU VALIDES]         liste des composants et références, confirmation obligatoire
      ↓
hw-footprint  +  hw-calculator        (en parallèle)
 empreintes KiCad      valeurs E12/E24, pistes, thermique
      ↓
hw-coder-skidl        script SKiDL, netlist
      ↓
hw-erc-drc            checklist électrique + ERC, verdict
      ↓
hw-documentalist      README, BOM, tableau de brochage
```

## Le point de contrôle composants

Après l'architecte et l'agent composant, l'orchestrateur **s'arrête et te demande
de confirmer** les composants retenus avec leurs références exactes. C'est
volontaire et non contournable : une erreur de composant détectée ici coûte une
question, détectée après fabrication elle coûte un tour de prototypage.

## Les 7 spécialistes (+ l'orchestrateur)

| Agent | Lit `data_sheets/` | Écrit | Rapport |
|---|---|---|---|
| `hw-architect` | **non** | non | `hw-architect.md` |
| `hw-component` | **oui, exclusif** | non | `hw-component-<reference>.md` (un par composant) |
| `hw-footprint` | non | `footprints.pretty/` | `hw-footprint.md` |
| `hw-calculator` | non | non | `hw-calculator.md` |
| `hw-coder-skidl` | non | **le circuit** | non |
| `hw-erc-drc` | non | non | `hw-erc-drc.md` |
| `hw-documentalist` | non | README | non |

## Comment l'agent cherche dans KiCad tout seul

Antigravity n'a pas d'outil de recherche KiCad, et les librairies KiCad vivent
**hors du dossier de travail** — or les accès fichiers d'un agent sont limités au
workspace. La solution est un index local, construit une fois :

```
python .agents/scripts/kicad_search.py --index
```

Ça écrit `.agents/cache/kicad_index.txt` DANS le projet : une ligne par empreinte
et par symbole disponible. À partir de là, l'agent cherche dans ce fichier, donc
sans jamais sortir du workspace et sans déclencher de demande de permission.

```
python .agents/scripts/kicad_search.py footprint "SOIC-8"
python .agents/scripts/kicad_search.py symbol "ESP32-C3"
```

Normalement l'index est déjà là : L'Atelier le construit à la préparation du
projet, parce que c'est justement l'opération qui doit sortir du workspace.
L'agent vérifie quand même son existence et le construit s'il manque.
Si les librairies KiCad sont introuvables, il s'arrête sur `BLOQUE` au lieu de
créer des empreintes à l'aveugle : il te demandera d'ouvrir le projet avec
`--add-dir` ou de définir les variables d'environnement.

L'index est un cache : régénère-le avec `--index` après une mise à jour de KiCad
ou l'ajout d'une librairie.

Aucun agent n'a le droit de deviner un nom d'empreinte ou de symbole : il passe
par ce script et recopie le résultat exact, à la casse près.

**Symbole de circuit intégré manquant** : si le symbole n'est pas dans
`kicad_libs/`, le codeur s'arrête et te le demande. Il n'inventera pas de
brochage de substitution et ne changera pas de composant tout seul. Si tu as un
script d'acquisition par référence fabricant, place-le en
`.agents/scripts/pcbparts.py` (niveau 3 : modèles ECAD et tarifs depuis
pcbparts.dev). L'ordre d'acquisition d'un modèle manquant est imposé :
librairies KiCad, recherche élargie, pcbparts.dev, création à la main en dernier
recours seulement. Voir aussi `.agents/scripts/kicad_fetch_part.py` (extraction d'un symbole des librairies
KiCad vers `kicad_libs/`) et il sera utilisé.

---

# Mode MÉCA

**Agent principal : `meca-orchestrateur`**

## Workflow

`/meca-piece` — conception d'une pièce ou d'un assemblage.

```
meca-lead          cahier des charges : base → ajouts → soustractions → finitions
      ↓
meca-materials     TOP 3 matériaux, procédé, épaisseurs de paroi minimales
      ↓
meca-designer      script CadQuery paramétrique
      ↓
meca-reviewer      exécution réelle du modèle + relecture, verdict
      ↓
 [TU VALIDES]      rendu dans cq-editor, et export STEP si tu le veux
```

Pour une simple correction sur une pièce existante, l'orchestrateur peut aller
directement au concepteur puis au vérificateur. Une modification chirurgicale n'a
pas besoin d'un nouveau cahier des charges.

## Les 4 spécialistes (+ l'orchestrateur)

| Agent | Écrit | Rapport |
|---|---|---|
| `meca-lead` | non | `meca-lead.md` |
| `meca-materials` | non | `meca-materials.md` |
| `meca-designer` | **les scripts** | non |
| `meca-reviewer` | non | `meca-reviewer.md` |

`meca-designer` est utilisable en direct pour une petite retouche.

## La vérification est réelle, pas mentale

Un script CadQuery finit par `show_object()`, qui n'existe que dans cq-editor : le
script n'est donc pas exécutable en ligne de commande. Le projet fournit un runner
qui bouche ce trou :

```
python .agents/scripts/cq_check.py pieces/boitier.py --attendu 120x60x40
```

Il exécute réellement le modèle, et rapporte les exceptions, la boîte englobante,
le volume et le nombre de solides. Il prévient notamment si la base n'est pas à
Z=0 (le piège du centrage par défaut) et si le volume est nul.

C'est ce qui permet de détecter une inversion d'arguments — `cylinder(20, 5)` au
lieu de `cylinder(5, 20)` — qu'aucune relecture ne voit, parce que le code est
syntaxiquement parfait.

`--attendu` compare les dimensions mesurées au cahier des charges à 2 % près.

## Ce que le mode ne fera pas

CadQuery modélise par la géométrie et les booléens. Les formes organiques et les
doubles courbures s'y expriment très mal : `meca-lead` te le dira franchement et
proposera une approche simplifiée plutôt que trois cents lignes de contournement.

Et le concepteur n'ajoutera jamais d'export STEP sans que tu le demandes.

---

# Installation

0. Le plus simple : créer le projet depuis L'Atelier. L'outil copie le kit,
   retire les deux familles inutiles, crée `.agent_reports/`, `data_sheets/`,
   `kicad_libs/`, complète le `.gitignore`, câble le garde-fou sur le bon
   interpréteur, enregistre l'environnement KiCad et construit l'index. Les
   étapes ci-dessous décrivent la même chose à la main.
1. Copier `AGENTS.md` et `.agents/` à la racine du dépôt.
2. Ouvrir `/agents` : les agents de la famille installée doivent apparaître
   (24 si le kit complet est en place, groupés par préfixe `code-`, `hw-`,
   `meca-`). `/skills` doit montrer les 6 skills, `/hooks` le garde-fou.
3. `.agents/hooks.json` appelle `python` : si ton système n'expose que
   `python3`, remplace-le. L'Atelier le fait automatiquement quand il prépare le
   projet.
4. Ajouter `.agent_reports/` au `.gitignore` si tu ne veux pas versionner les
   rapports.
5. Mode hardware : créer `data_sheets/` et y placer les JSON avec leurs dossiers
   d'images.
6. Si KiCad est installé dans un emplacement non standard, définir
   `KICAD8_FOOTPRINT_DIR` et `KICAD8_SYMBOL_DIR`, ou ajouter le dossier au
   workspace avec `--add-dir`.

## Si tu n'utilises qu'un seul domaine

Supprime les dossiers des deux autres familles dans `.agents/agents/` et leurs
workflows. Le protocole commun et le garde-fou restent valables tels quels.

# Ce que le dispositif ne garantit pas

Le périmètre « lecture seule » d'un agent d'audit repose sur son prompt et sa liste
d'outils, pas sur un verrou : il a `write_to_file` pour publier son rapport, donc
rien ne l'empêche techniquement d'écrire ailleurs. La charge utile d'un hook ne
contient pas le nom de l'agent appelant, il est donc impossible d'écrire une règle
« si l'agent est `hw-component`, refuse toute écriture hors `.agent_reports/` ».

Le garde-fou couvre en revanche tout ce qui ne dépend pas de l'appelant :
commandes destructives, fichiers de secrets, `data_sheets/`, et modification des
définitions d'agents elles-mêmes.
