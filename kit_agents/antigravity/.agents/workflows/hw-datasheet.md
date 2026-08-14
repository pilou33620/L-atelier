---
description: Analyse d'un ou plusieurs composants a partir des datasheets JSON, sans conception
---

# /hw-datasheet

Mode consultation de datasheets. Sert quand on veut juste connaître les
caractéristiques d'un composant, sans concevoir de carte.

## 1. Inventaire

`list_dir` sur `data_sheets/` pour lister les composants disponibles. Si le
composant demandé n'y est pas, le dire immédiatement et demander le fichier JSON à
l'utilisateur : aucun agent ne doit deviner un brochage.

## 2. Extraction

Invoquer `hw-component` avec l'identifiant de mission et la liste précise de ce
qu'on cherche (brochage, tensions, découplage, adresse I2C, limites absolues...).

Pour plusieurs composants indépendants, les lancer en parallèle : un sous-agent
par composant.

## 3. Restitution

Lire la fiche `.agent_reports/hw-component-<reference>.md` et restituer la
synthèse à l'utilisateur, en
conservant les références de source (`fichier.json, page N`) pour qu'il puisse
vérifier dans le PDF d'origine.

Ce workflow ne produit aucun fichier de circuit. S'il faut concevoir, c'est
`/hw-carte`, avec un nouvel identifiant de mission.
