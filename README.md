# L'Atelier

L'Atelier est une plateforme logicielle complète (V4.5.0) conçue pour la conception assistée par intelligence artificielle (agents Antigravity) dans trois domaines majeurs :
- **Code** : Conception et modification de projets logiciels.
- **Hardware (Électronique)** : Conception de cartes électroniques, intégration avec KiCad et SKiDL.
- **Mécanique (Pièces 3D)** : Conception paramétrique avec CadQuery.

## Fonctionnalités Principales

- **Interface Multi-onglets** : Éditeur de code intégré, explorateur de fichiers et journal des agents.
- **Environnement Isolé** : Exécution des scripts et des agents dans des bacs à sable (sandboxes) avec support Docker pour la sécurité.
- **Génération de Graphes Structurels** : Utilisation de `Graphify` pour l'analyse de code.
- **Intégration KiCad / SKiDL** : Synchronisation des bibliothèques, recherche de composants, génération de netlists.
- **Support Multi-Agents (Antigravity)** : Intégration profonde avec les agents IA pour automatiser la génération de code, la recherche de datasheets, et la manipulation des fichiers de conception.

## Architecture du Projet (Python)

L'organisation des modules Python du projet s'articule autour d'une interface graphique principale, et de scripts de préparation dédiés aux agents IA.

```text
L'atelier IA/
├── main.py : Point d'entrée principal de l'application lançant l'interface utilisateur.
├── ui.py : Interface utilisateur principale de l'IDE orchestrant les différentes vues.
├── scaffold_projet.py : Script de préparation (scaffolding) et configuration de l'environnement des agents.
├── pcbparts.py : Client API pour la recherche et la tarification des composants électroniques.
├── convertisseur PDF-Json.py : Outil autonome (Tkinter) pour convertir les fiches techniques PDF en JSON (pour ingestion IA).
├── requirements.txt : Liste des dépendances et bibliothèques Python nécessaires au projet.
├── README.md : Documentation principale de présentation du projet (ce fichier).
├── MANUEL.md : Manuel d'utilisation détaillé des différentes fonctionnalités de l'outil.
└── kit_agents/ : Dossier contenant les configurations par défaut et modèles pour les agents.
    ├── AGENTS.md : Documentation et descriptions des agents disponibles.
    ├── agents_markdown_combine.txt : Fichier combiné des prompts et configurations d'agents.
    ├── workflows_markdown_combine.txt : Fichier combiné décrivant les flux de travail par défaut.
    └── .agents/ : Structure type d'intégration des agents pour les projets.
        ├── agents/ : Définitions individuelles de chaque agent (rôles, compétences, par domaine : code, hardware, meca).
        ├── hooks/ : Scripts d'interception (ex: garde_fou.py pour la sécurité des agents).
        ├── scripts/ : Scripts utilitaires exécutables par les agents (recherche KiCad, validation CadQuery, etc.).
        ├── skills/ : Base de compétences métier (CadQuery, KiCad SKiDL, vérification Python, etc.).
        └── workflows/ : Scénarios et flux de travail guidés pour les agents (audit, création de carte, pièce mécanique, etc.).
```

## Outils Inclus

- `convertisseur PDF-Json.py` : Un outil autonome doté d'une interface graphique pour convertir les fiches techniques PDF en format JSON hybride (texte Markdown et extraction des images), spécifiquement pensé pour l'ingestion par les agents IA.
- Client `pcbparts` : Recherche et tarification des composants électroniques via l'API pcbparts.dev.
- Module de Scaffolding : Prépare automatiquement l'environnement de vos projets pour être prêt à accueillir les agents Antigravity (`.agents/`, configs).

## Installation

1. Clonez ce dépôt.
2. Installez les dépendances Python via pip :
   ```bash
   pip install -r requirements.txt
   ```
3. (Optionnel mais recommandé) Installez [Docker](https://www.docker.com/) pour permettre l'exécution des scripts générés dans un environnement parfaitement isolé.
4. Assurez-vous d'avoir les outils annexes selon vos besoins (KiCad pour le mode Hardware, CadQuery pour le mode Mécanique, Graphify pour le graphe de code).

## Lancement

Exécutez le point d'entrée de l'application :

```bash
python main.py
```
