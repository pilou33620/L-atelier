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
├── ui_coder.py : Module de l'interface spécifique à l'onglet de l'agent codeur.
├── ui_general.py : Module de l'interface pour le chat avec l'assistant général.
├── ui_hardware.py : Module de l'interface dédié à l'agent de conception électronique (Hardware).
├── ui_meca.py : Module de l'interface gérant l'agent de conception mécanique 3D (Meca).
├── requirements.txt : Liste des dépendances et bibliothèques Python nécessaires au projet.
├── README.md : Documentation principale de présentation du projet (ce fichier).
├── MANUEL.md : Manuel d'utilisation détaillé des différentes fonctionnalités de l'outil.
├── CHANGELOG.md : Historique des modifications, mises à jour et correctifs du projet.
├── core/ : Moteur principal de l'application (LLM, orchestration, outils).
│   ├── llm.py : Gestion des connexions et interactions avec les modèles de langage (API et local).
│   ├── nodal_graph.py : Gestionnaire du graphe nodal pour l'exécution d'agents en mode Graphify.
│   ├── nodal_graph_original.py : Version originale de sauvegarde du système de graphe nodal.
│   ├── rag_engine.py : Moteur de RAG (Retrieval-Augmented Generation) pour la recherche documentaire.
│   ├── sandbox.py : Environnement sécurisé contrôlant les opérations de lecture/écriture sur les fichiers.
│   ├── utils.py : Fonctions utilitaires transverses utilisées à travers l'application.
│   └── workers.py : Définition des tâches asynchrones pour éviter de bloquer l'interface graphique.
├── coder/ : Configuration des agents logiciels.
│   └── agents.json : Définition des rôles, outils et prompts de l'équipe de développement.
├── general/ : Configuration de l'assistant général.
│   └── agents.json : Paramètres et prompt de l'assistant IA généraliste.
├── hardware/ : Outils et agents pour la conception électronique.
│   ├── agents_hardware.json : Configuration des agents spécialisés dans le design hardware.
│   ├── agents_skidl.json : Configuration de l'agent dédié à la génération de schémas avec SKiDL.
│   └── convertisseur PDF-Json.py : Script utilitaire pour extraire les données de datasheets PDF.
├── meca/ : Outils et agents pour la conception mécanique 3D.
│   ├── agents_meca.json : Configuration des agents en charge de la modélisation CAO.
│   └── cadquery_commands.json : Base de données des commandes CadQuery pour l'agent mécanicien.
├── skills/ : Base de compétences métier (déclenchables avec / dans le chat).
│   ├── audit_secu.md : Instructions de l'expert pour l'audit de sécurité du code.
│   ├── materials_selection.md : Compétence pour l'aide au choix des matériaux en mécanique.
│   ├── refactor.md : Instructions pour le refactoring et l'optimisation du code.
│   ├── review.md : Skill générique pour la revue de code logiciel.
│   ├── review_hw.md : Skill pour la vérification technique des conceptions électroniques.
│   ├── review_meca.md : Skill pour l'analyse des modèles CAO et contraintes physiques.
│   ├── review_ui.md : Compétence dédiée à l'évaluation des interfaces utilisateur.
│   └── test.md : Instructions pour la conception et validation de tests unitaires.
└── tests/ : Suite de tests unitaires du projet.
    ├── test_llm.py : Tests validant la communication avec les modèles de langage.
    ├── test_nodal_graph.py : Tests vérifiant la bonne exécution des graphes nodaux.
    ├── test_rag_engine.py : Tests pour le moteur de recherche et d'indexation documentaire.
    ├── test_sandbox.py : Tests assurant la robustesse et la sécurité de la sandbox.
    ├── test_utils.py : Tests des fonctions utilitaires diverses.
    └── test_workers.py : Tests des processus parallèles et tâches d'arrière-plan.
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
