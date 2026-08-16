# Contexte projet — Claude Code

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
| Exécution d'un script du projet | `python .claude/scripts/run_projet.py circuits/<nom>.py` |
| Modèle ECAD manquant (niveau 3) | `python .claude/scripts/pcbparts.py disponible "<réf>"` puis `installer "<réf>" --projet .` |
| Vérification modèle 3D | `python .claude/scripts/cq_check.py <script.py>` |
| Requête sur le graphe de code | `python .claude/scripts/graph_query.py <commande> <cible>` |
| Index des librairies KiCad | `python .claude/scripts/kicad_search.py --index` |
| Recherche empreinte KiCad | `python .claude/scripts/kicad_search.py footprint "<motif>"` |
| Recherche symbole KiCad | `python .claude/scripts/kicad_search.py symbol "<motif>"` |
| Gestionnaire d'entrée & mémoire | `python .claude/scripts/spec_ingress.py --history` |

Le formatage ne doit jamais être lancé sur tout le dépôt d'un coup : un
reformatage global noie le diff et rend la revue impossible.

## Convention de nommage des tests

- Dossier des tests : `tests/`
- Motif des fichiers : `test_*.py`

## Passerelle d'entrée transversale (Step 0)

Avant même l'intervention d'un orchestrateur, l'agent **`spec-translator`** (Passerelle d'entrée) ingère les demandes et cahiers des charges rédigés en français, résout le contexte conversationnel (fenêtre glissante des 2-3 derniers tours) et mappe les fichiers réels du projet pour produire une spécification technique standardisée en anglais dans `.agent_reports/spec_ingress.md`.

## Les trois modes & Commandes Slash Claude Code

| Mode | Agent principal | Commandes slash (`.claude/commands/`) | Domaine |
|---|---|---|---|
| **Code** | `code-orchestrateur` | `/code-feature` `/code-bugfix` `/code-audit` `/code-retrocompat` | logiciel Python |
| **Hardware** | `hw-orchestrateur` | `/hw-carte` `/hw-datasheet` | cartes électroniques, SKiDL, KiCad |
| **Méca** | `meca-orchestrateur` | `/meca-piece` | pièces et assemblages 3D, CadQuery |

Chaque famille est étanche : un orchestrateur ne délègue qu'aux spécialistes de
son domaine. Le manuel complet est dans `.claude/MANUEL.md`.

**Règle d'implémentation multi-fichiers (> 2 fichiers)** : Tout lot de 3 fichiers ou plus est obligatoirement découpé en passes séquentielles ordonnées par l'Architecte et exécuté passe par passe par l'Orchestrateur (un appel codeur dédié par fichier avec contrôle intermédiaire) afin de garantir un contexte propre et sans pollution.


## Protocole Multi-Agents & Rapports Déterministes

Tous les rapports sont stockés dans `.agent_reports/<agent_name>.md` :
- plan d'architecture -> `.agent_reports/code-architect.md` (ou `hw-architect.md`)
- revue -> `.agent_reports/code-reviewer.md` (ou `meca-reviewer.md`)
- diagnostic bug -> `.agent_reports/code-debugger.md`
- composants & pinouts -> `.agent_reports/hw-component.md`
- calculs électroniques -> `.agent_reports/hw-calculator.md`
- rapport ERC/DRC -> `.agent_reports/hw-erc-drc.md`
- validation méca -> `.agent_reports/meca-reviewer.md`

En-tête obligatoire sur chaque rapport :
```markdown
<!-- mission: <identifiant-de-mission> | agent: <nom-agent> | date: AAAA-MM-JJ -->
```

Verdicts stricts : `APPROUVE`, `CORRECTIONS_REQUISES`, `BLOQUE`, `VALIDATION_VISUELLE_REQUISE`, `RIEN_A_SIGNALER`.

## Datasheets (mode hardware)

Les datasheets sont pré-extraites à la racine du projet dans `data_sheets/` :
- `data_sheets/<composant>.json` : tableau de pages `[{page, texte_markdown, images}]`
- `data_sheets/<composant>_images/` : captures extraites du PDF

**`data_sheets/` est en lecture seule pour tous les agents**, et seul `hw-component` a le droit d'ouvrir ce dossier.

## Environnement d'exécution

Les chemins des librairies KiCad sont enregistrés par L'Atelier dans `.claude/cache/env.json` (ou `.agents/cache/env.json`). Tout script du projet s'exécute via `python .claude/scripts/run_projet.py <script>`.

## Graphe de code (mode code)

Si Graphify est exécuté, la synthèse est dans `graphify-out/GRAPH_REPORT.md` (en lecture seule).
Interrogation ciblée : `python .claude/scripts/graph_query.py`.
