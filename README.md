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
