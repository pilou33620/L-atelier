# L'Atelier

L'Atelier est une plateforme logicielle complète (V4.5.0) conçue pour la conception assistée par intelligence artificielle — avec support natif pour **Antigravity (Gemini)** et **Claude Code (Claude)** — dans trois domaines majeurs :
- **Code** : Conception et modification de projets logiciels Python.
- **Hardware (Électronique)** : Conception de cartes électroniques, intégration avec KiCad et SKiDL.
- **Mécanique (Pièces 3D)** : Conception paramétrique avec CadQuery.

## Fonctionnalités Principales

- **Support Bi-Outils IA** : Choisissez entre **Antigravity (Gemini)** (`.agents/`, `AGENTS.md`) et **Claude Code (Claude)** (`.claude/`, `CLAUDE.md`, commandes slash natives).
- **Interface Multi-onglets** : Éditeur de code intégré, explorateur de fichiers et journal d'exécution.
- **Environnement Isolé** : Exécution des scripts et des agents dans des bacs à sable (sandboxes) avec support Docker pour la sécurité.
- **Génération de Graphes Structurels** : Utilisation de `Graphify` pour l'analyse et la navigation du code.
- **Intégration KiCad / SKiDL** : Synchronisation des bibliothèques, recherche de composants, génération de netlists.
- **Écosystème de 25 Agents Spécialisés** : Rôles dédiés par domaine (architecte, codeur, reviewer, calculs, pinouts, DRC/ERC, matériaux méca...).

## Architecture du Projet (Python)

```text
L'atelier IA/
├── main.py : Point d'entrée principal de l'application lançant l'interface utilisateur.
├── ui.py : Interface utilisateur principale de l'IDE orchestrant les différentes vues.
├── scaffold_projet.py : Script de préparation (scaffolding) et configuration de l'environnement des agents (Antigravity / Claude Code).
├── pcbparts.py : Client API pour la recherche et la tarification des composants électroniques.
├── convertisseur PDF-Json.py : Outil autonome (Tkinter) pour convertir les fiches techniques PDF en JSON (pour ingestion IA).
├── requirements.txt : Liste des dépendances et bibliothèques Python nécessaires au projet.
├── README.md : Documentation principale de présentation du projet.
├── MANUEL.md : Manuel d'utilisation détaillé des fonctionnalités.
└── kit_agents/ : Dossier contenant les modèles d'agents pour les 2 outils IA :
    ├── antigravity/ : Kit complet pour Antigravity (Gemini)
    │   ├── AGENTS.md : Contrat de référence Antigravity.
    │   └── .agents/ : Structure d'agents, skills, scripts, hooks et workflows.
    └── claude_code/ : Kit complet pour Claude Code (Claude)
        ├── CLAUDE.md : Consignes de projet pour Claude Code.
        ├── AGENTS.md : Contrat multi-agents.
        └── .claude/ : Agents adaptés (View/Edit/Bash/Task), commandes slash (.claude/commands/), skills et scripts.
```

## Outils Inclus

- `convertisseur PDF-Json.py` : Outil autonome doté d'une interface graphique pour convertir les fiches techniques PDF en format JSON hybride (texte Markdown et extraction des images), spécifiquement pensé pour l'ingestion par les agents IA.
- Client `pcbparts` : Recherche et tarification des composants électroniques via l'API pcbparts.dev.
- Module de Scaffolding (`scaffold_projet.py`) : Prépare automatiquement l'environnement de vos projets pour accueillir les agents Antigravity ou Claude Code.

## Installation

1. Clonez ce dépôt.
2. Installez les dépendances Python via pip :
   ```bash
   pip install -r requirements.txt
   ```
3. (Optionnel mais recommandé) Installez [Docker](https://www.docker.com/) pour permettre l'exécution des scripts générés dans un conteneur isolé.
4. Assurez-vous d'avoir les outils annexes selon vos besoins (KiCad pour le mode Hardware, CadQuery pour le mode Mécanique, Graphify pour le graphe de code).

## Lancement

Exécutez le point d'entrée de l'application :

```bash
python main.py
```
