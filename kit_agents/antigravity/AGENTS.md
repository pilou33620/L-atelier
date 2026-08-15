# Contexte projet

Ce dépôt utilise trois familles d'agents spécialisés, une par domaine :
**code**, **hardware** (cartes électroniques) et **méca** (pièces 3D).

## Stack

- Langage : Python
- Gestionnaire de paquets : pip
- Tests : pytest
- Hardware : SKiDL + KiCad 8 ou 9 (les scripts détectent la version installée)
- Méca : CadQuery 2.x (visualisation dans cq-editor)

## Commandes de vérification

**Section critique.** C'est la SEULE source autorisée pour les commandes de
vérification. Aucun agent ne doit deviner une chaîne d'outils.

| Rôle | Commande |
|---|---|
| Syntaxe / compilation | `python -m compileall -q .` |
| Lint | `ruff check .` |
| Formatage | `ruff format .` |
| Tests | `pytest -q` |
| Diff en cours | `git diff` / `git diff --staged` |
| Exécution d'un script du projet | `python .agents/scripts/run_projet.py circuits/<nom>.py` |
| Modèle ECAD manquant (niveau 3) | `python .agents/scripts/pcbparts.py disponible "<réf>"` puis `installer "<réf>" --projet .` |
| Vérification modèle 3D | `python .agents/scripts/cq_check.py <script.py>` |
| Requête sur le graphe de code | `python .agents/scripts/graph_query.py <commande> <cible>` |
| Index des librairies KiCad | `python .agents/scripts/kicad_search.py --index` |
| Recherche empreinte KiCad | `python .agents/scripts/kicad_search.py footprint "<motif>"` |
| Recherche symbole KiCad | `python .agents/scripts/kicad_search.py symbol "<motif>"` |

Le formatage ne doit jamais être lancé sur tout le dépôt d'un coup : un
reformatage global noie le diff et rend la revue impossible.

## Convention de nommage des tests

- Dossier des tests : `tests/`
- Motif des fichiers : `test_*.py`

## Les trois modes

| Mode | Agent principal | Workflows | Domaine |
|---|---|---|---|
| **Code** | `code-orchestrateur` | `/code-feature` `/code-bugfix` `/code-audit` `/code-retrocompat` | logiciel Python |
| **Hardware** | `hw-orchestrateur` | `/hw-carte` `/hw-datasheet` | cartes électroniques, SKiDL, KiCad |
| **Méca** | `meca-orchestrateur` | `/meca-piece` | pièces et assemblages 3D, CadQuery |

Chaque famille est étanche : un orchestrateur ne délègue qu'aux spécialistes de
son domaine. Le manuel complet est dans `.agents/MANUEL.md`.

**Règle d'implémentation multi-fichiers (> 2 fichiers)** : Tout lot de 3 fichiers ou plus est obligatoirement découpé en passes séquentielles ordonnées par l'Architecte et exécuté passe par passe par l'Orchestrateur (un appel codeur dédié par fichier avec vérification intermédiaire sur disque) afin de garantir un contexte propre et sans pollution.


## Datasheets (mode hardware)

Les datasheets sont pré-extraites à la racine du projet :

```
data_sheets/
  <composant>.json          tableau de pages [{page, texte_markdown, images}]
  <composant>_images/       captures extraites du PDF d'origine
```

Les chemins d'images listés dans le JSON sont déjà relatifs à la racine du
projet : ils s'utilisent tels quels.

**`data_sheets/` est en lecture seule pour tous les agents**, et cette règle est
appliquée par le garde-fou, pas seulement par les consignes. Seul `hw-component` a
le droit d'ouvrir ce dossier : tous les autres agents hardware travaillent à
partir de son rapport. Cette contrainte existe pour préserver leur contexte, une
datasheet faisant couramment plusieurs centaines de pages.

## Environnement d'exécution

Les chemins des librairies KiCad sont enregistrés par L'Atelier dans
`.agents/cache/env.json`. Ils ne sont PAS dans l'environnement des agents : un
`python <script>` nu ne les voit pas. Tout script du projet s'exécute donc via
`python .agents/scripts/run_projet.py <script>`, qui réinjecte ces variables.

Si `.agents/cache/env.json` est absent, aucun agent ne le fabrique : c'est le
signe que la préparation du projet n'a pas été faite, et il faut le dire à
l'utilisateur.

## Graphe de code (mode code)

Si le projet a été analysé par Graphify, sa sortie est à la racine :

```
graphify-out/
  GRAPH_REPORT.md    synthèse lisible : composants, god nodes, clusters
  graph.json         graphe complet, à interroger via script uniquement
  graph.html         visualisation pour l'humain, jamais pour un agent
```

Les agents du mode code s'en servent pour localiser le code et mesurer l'impact
d'une modification, au lieu de reconstruire la structure du projet à chaque
mission. `graph.json` ne se lit jamais directement (plusieurs mégaoctets) : il
s'interroge avec `.agents/scripts/graph_query.py`.

**`graphify-out/` est en lecture seule pour tous les agents**, appliqué par le
garde-fou : c'est une sortie générée, la modifier à la main fausse le graphe sans
toucher au code.

Deux règles non négociables : une relation `INFERRED` est une hypothèse à vérifier
au `grep_search` avant d'agir, et un graphe plus ancien que les dernières
modifications du code n'est fiable que pour la cartographie générale. Le graphe
localise, le fichier confirme, les tests valident.

Le graphe est optionnel : sans lui, les agents retombent sur `grep_search`.

## Convention de rapports

Les analyses des agents sont écrites dans `.agent_reports/<nom-agent>.md`. Ces
chemins sont déterministes : les lire plutôt que de redemander une analyse.

Chaque rapport commence par un en-tête de mission :

```
<!-- mission: AAAA-MM-JJ-slug | agent: <nom> | date: AAAA-MM-JJ -->
```

**Un rapport dont l'identifiant de mission ne correspond pas à la mission en cours
est périmé et doit être traité comme inexistant.** Les chemins étant réutilisés
d'une mission à l'autre, il y a presque toujours un rapport de la mission
précédente sur le disque.

Ajouter `.agent_reports/`, `.agent_backups/`, `.agents/cache/` et
`graphify-out/` au `.gitignore` : rapports, sauvegardes de l'éditeur, index KiCad
et graphe de code sont des données locales régénérables. L'Atelier s'en charge à
la création du projet.

## Sécurité

- Ne jamais commiter de secrets, de clés d'API ni de fichiers `.env`.
- Ne jamais lancer de commande destructive (`rm -rf`, `git reset --hard`,
  `git push --force`, `git clean -f`) sans confirmation explicite.
- Ne jamais modifier l'historique git déjà poussé.
- Ne jamais modifier `data_sheets/`.
- Les agents en lecture seule n'écrivent que leur propre rapport.

Ces règles ne sont pas seulement des consignes : `.agents/hooks.json` installe un
garde-fou `PreToolUse` qui refuse effectivement les commandes destructives et
l'écriture dans les fichiers de secrets comme dans `data_sheets/`.

## Règle transversale : ne jamais inventer une valeur physique

Un numéro de broche, une adresse I2C, une tension, une cote en millimètres ou une
propriété de matériau inventés ne produisent pas une erreur visible : ils
produisent un objet fabriqué et faux. Tout agent qui ne trouve pas une valeur le
dit et s'arrête, plutôt que de combler le trou.

## Règle transversale : nettoyage des fichiers temporaires

Si un agent est amené à écrire des bouts de code, des scripts ou des fichiers pour effectuer des tests ou des modifications, **il doit impérativement nettoyer et supprimer ces fichiers temporaires après usage**. L'espace de travail ne doit pas être pollué par des fichiers inutiles ou obsolètes une fois la tâche de l'agent terminée.
