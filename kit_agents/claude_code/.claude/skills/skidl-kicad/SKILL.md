---
name: skidl-kicad
description: >
  Règles d'or pour écrire du code SKiDL propre et générer un netlist KiCad 8
  sans erreur : instanciation des composants, connexion par nom de broche, nets
  explicites, bus, sous-circuits, NC, ordre de routage (alimentations puis
  signaux), ERC. À charger avant d'écrire ou de modifier un script SKiDL, de
  chercher une empreinte KiCad, ou de relire un circuit décrit en Python.
---

# SKiDL et KiCad 8 : règles d'or

## 1. Instanciation des composants (anti-hallucination)

Considère TOUS les circuits intégrés comme NON standards : LDO, régulateurs,
MCU, capteurs, drivers, mémoires. Seuls les passifs de base sont standards :
résistances, condensateurs, inductances, LED, diodes courantes, connecteurs
génériques.

- **Passifs standards** -> librairies KiCad 8 natives (`Device:R`, `Device:C`...).
- **Tout circuit intégré** -> le symbole doit exister localement AVANT d'être
  instancié. Vérifie sa présence :

```
find_by_name  pattern: *.kicad_sym  dans kicad_libs/
```

Si le symbole existe :

```python
u1 = Part('kicad_libs/NOM_COMPOSANT.kicad_sym', 'NOM_COMPOSANT',
          footprint='<Librairie>:<Empreinte>')   # nom rendu par kicad_search
```

Le symbole et l'empreinte sont deux choses séparées : `kicad_libs/` ne contient
que des symboles. Le nom d'empreinte se cherche (section 2) et se recopie tel
quel ; ne le fabrique pas à partir du nom du symbole.

S'il n'existe pas, recopie-le depuis les librairies KiCad installées, en deux
temps — jamais de nom deviné :

```
run_command: python .claude/scripts/kicad_fetch_part.py chercher "ESP32-C3-MINI"
run_command: python .claude/scripts/kicad_fetch_part.py copier "RF_Module:ESP32-C3-MINI-1"
```

Le script écrit `kicad_libs/<NOM>.kicad_sym` avec les sous-unités et le symbole
parent si le composant en dérive.

Si la recherche ne renvoie rien, le composant n'est pas dans les librairies
installées : **n'invente ni le nom du symbole ni son brochage.** Un symbole
inventé produit un netlist qui compile et un circuit imprimé faux. Termine par
`BLOQUE` en donnant à l'utilisateur la commande exacte à lancer, et le brochage
relevé dans la datasheet pour qu'il puisse créer le symbole lui-même.

## 1 bis. Ordre d'acquisition d'un modèle manquant

Symbole comme empreinte, l'ordre est imposé et aucun niveau ne se saute :

| Niveau | Source | Commande |
|---|---|---|
| 1 | librairies KiCad installées | `kicad_search.py` / `kicad_fetch_part.py` |
| 2 | même recherche, élargie (famille, cotes, synonymes de boîtier) | idem |
| 3 | pcbparts.dev / SamacSys | `pcbparts.py disponible` puis `installer` |
| 4 | demander à l'utilisateur, créer à la main s'il le demande | — |

Créer un modèle à la main est le niveau le plus lent et le plus risqué : cotes à
ressaisir, aucune relecture. Il n'arrive qu'après épuisement des trois autres, et
l'origine retenue se consigne dans le rapport.

## 2. Recherche d'empreinte : ne devine jamais

Le nom d'une empreinte KiCad ne se déduit pas, il se cherche. Utilise le script
fourni :

```
run_command: python .claude/scripts/kicad_search.py footprint "SOIC-8"
run_command: python .claude/scripts/kicad_search.py symbol "ESP32"
```

Il retourne les vrais noms au format `Librairie:Empreinte`. Reporte-les
exactement, à la casse près.

Deux origines possibles, et elles se traitent pareil :

- **empreinte des librairies KiCad** : `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`,
  `RF_Module:ESP32-C3-MINI-1`… La grande majorité des cas.
- **empreinte fournie par l'utilisateur** : un `.kicad_mod` déposé dans
  `footprints.pretty/` du projet. Le nom de librairie est alors le nom du dossier
  sans son suffixe, donc `footprints:MON_EMPREINTE`. Ce dossier est cherché AVANT
  les librairies globales.

Dans les deux cas, tu recopies le nom rendu par le script. Tu ne le construis
jamais toi-même.

Si le script te répond qu'il a trouvé « hors index », c'est que l'index est
périmé — probablement parce que l'utilisateur vient d'ajouter ses empreintes. Le
résultat est valable ; signale simplement dans ton rapport que l'index gagnerait
à être reconstruit.

### L'index local, à vérifier en premier

Les librairies KiCad vivent HORS du dossier de travail. Pour éviter une demande
de permission à chaque recherche, le projet en garde un index dans le workspace :
`.agents/cache/kicad_index.txt`.

Avant ta première recherche, vérifie qu'il existe (`list_dir` sur
`.agents/cache/`). S'il est absent, construis-le :

```
run_command: python .claude/scripts/kicad_search.py --index
```

Si cette commande échoue en annonçant qu'aucune librairie KiCad n'a été trouvée,
**n'improvise pas** : termine par `BLOQUE` en demandant à l'utilisateur soit
d'ouvrir le projet avec `--add-dir <dossier des librairies KiCad>`, soit de
renseigner les chemins KiCad dans L'Atelier (qui écrit `KICAD9_FOOTPRINT_DIR` et
`KICAD9_SYMBOL_DIR`, ou leurs équivalents `KICAD8_*`). Créer vingt empreintes à
la main parce que l'index est absent est une catastrophe silencieuse.

Une fois l'index présent, tu peux aussi le fouiller directement avec
`grep_search` : c'est un simple fichier texte, une ligne par entrée. Utile pour
compter les variantes d'un boîtier avant de choisir.

L'index est un cache : s'il date d'avant une mise à jour de KiCad ou l'ajout
d'une librairie, `--index` le régénère.

Si le script ne trouve rien : essaie des synonymes et des boîtiers génériques
(`SOIC-8_3.9x4.9mm_P1.27mm`, `TSSOP-16`, `QFN-24-1EP_4x4mm`...) AVANT de
conclure qu'il faut créer l'empreinte. Créer une empreinte de zéro est le
dernier recours, jamais le premier réflexe.

## 3. Les six règles de connexion

1. **Brochage par NOM, jamais par numéro.** `u1['GND']`, pas `u1[4]`. Les noms
   viennent des fiches `.agent_reports/hw-component-*.md`, pas de ta mémoire.
2. **Nets explicites.** Ne connecte jamais deux broches directement entre elles
   (`c1[1] += u1[2]` est interdit). Crée toujours le net d'abord :
   ```python
   vcc_3v3 = Net('3V3')
   vcc_3v3 += u1['VDD'], c1[1]
   ```
   Un net nommé est débogable dans KiCad ; une connexion directe ne l'est pas.
3. **Syntaxe idiomatique.** L'opérateur `+=` pour connecter, `Bus()` pour les
   lignes parallèles (I2C, SPI, bus de données, adresses).
4. **Sous-circuits.** Au-delà de 10 composants, encapsule chaque bloc logique
   (alimentation, horloge, interface, capteur) dans une fonction décorée
   `@subcircuit`.
5. **Valeurs sur les passifs.** Toujours l'attribut `value` :
   `R(value='10k')`, `C(value='100nF')`. Une résistance sans valeur est une
   erreur de nomenclature garantie.
6. **NC explicite.** Marque les broches volontairement inutilisées :
   `u1['EN'] += NC`. Sans ça, l'ERC signale des broches flottantes et on ne
   distingue plus les vrais oublis des choix assumés.

## 4. Ordre de routage

Toujours dans cet ordre, jamais mélangé :

1. Instancier tous les composants avec leurs valeurs et empreintes exactes.
2. Router les alimentations : créer `GND`, puis les rails (`3V3`, `5V`, `VIN`),
   et connecter TOUTES les broches de masse et d'alimentation.
3. Router les signaux (données, horloges, interruptions, resets).
4. Terminer le script par `ERC()` puis
   `generate_netlist(file_='circuits/<nom>.net')`. L'argument `file_` est
   obligatoire : sans lui le netlist atterrit à la racine du projet.

Router les signaux avant les alimentations est la façon la plus fiable
d'oublier une broche de masse.

## 5. Structure et nommage du script

**Emplacement imposé : `circuits/<nom-de-la-carte>.py`**, en minuscules avec des
tirets — `circuits/carte-capteur.py`, `circuits/chargeur-lipo.py`. Un fichier par
carte. Les fichiers produits portent le même nom de base, à côté :

```
circuits/carte-capteur.py           le script SKiDL
circuits/carte-capteur.net          le netlist
circuits/carte-capteur.erc          le rapport ERC
circuits/carte-capteur.log          le journal SKiDL
circuits/carte-capteur_sklib.py     sauvegarde des symboles utilisés
```

Les trois derniers sont produits automatiquement par SKiDL, nommés d'après le
script, et rangés à côté de lui par `run_projet.py`. Tu n'as rien à faire pour
eux — mais **le netlist, si** : `ERC()` n'accepte pas de chemin, alors que
`generate_netlist()` en accepte un. Sans argument explicite, le netlist tombe
dans le répertoire courant, c'est-à-dire à la racine du projet.

Ce n'est pas de la cosmétique : les rapports d'agents, les relances de mission et
le bouton d'exécution de L'Atelier désignent tous ce fichier par son chemin. Un
script à la racine ou au nom improvisé oblige chaque relecteur à le chercher.

À l'intérieur, sépare visuellement, avec des commentaires de section : paramètres
et valeurs, instanciation, alimentations, signaux, ERC et export. Un script SKiDL
qui mélange les trois est illisible dès 20 composants.

Vérification syntaxique : `python -m compileall -q .` puis exécution du script
lui-même, qui produit le netlist et le rapport ERC.

## 6. Acquisition d'un symbole absent

`.claude/scripts/kicad_fetch_part.py` recopie un symbole des librairies KiCad
installées vers `kicad_libs/`. Il ne télécharge rien et ne crée rien : il extrait
un symbole qui existe déjà, avec ses sous-unités et son symbole parent s'il en
dérive.

```
python .claude/scripts/kicad_fetch_part.py chercher "<référence ou boîtier>"
python .claude/scripts/kicad_fetch_part.py copier "<Librairie>:<Nom>"
```

Toujours dans cet ordre : `chercher` d'abord, pour obtenir le nom exact, puis
`copier` en recopiant ce nom à l'identique. Vérifie ensuite que
`kicad_libs/<Nom>.kicad_sym` existe avant d'instancier.

Le script lit les librairies KiCad, qui sont hors du workspace : l'accès peut
t'être refusé selon la configuration. Ce n'est pas un échec de conception.

Si la recherche ne renvoie rien, ou si l'accès est refusé : **arrête-toi.**
Termine par `BLOQUE` en indiquant la référence manquante, la commande exacte à
lancer, et le brochage relevé dans la datasheet. L'utilisateur la lancera depuis
L'Atelier (bouton « Importer un symbole ») ou créera le symbole dans KiCad.
N'invente pas de brochage de substitution et ne remplace pas le composant par un
autre de ta propre initiative.

## 7. Modèles et tarifs importés de pcbparts.dev

L'Atelier peut télécharger un symbole, une empreinte et les tarifs d'un
composant depuis pcbparts.dev (JLCPCB/LCSC pour les prix, SamacSys pour les
modèles ECAD). Le résultat arrive dans le projet sous trois formes :

- `kicad_libs/<REF>.kicad_sym` — le symbole, utilisable directement ;
- `footprints.pretty/<NOM>.kicad_mod` — l'empreinte, référencée
  `footprints:<NOM>` ;
- `.agent_reports/pcbparts-<ref>.md` — référence fabricant, code LCSC, boîtier,
  type de librairie JLCPCB, prix par palier, stock, lien datasheet.

Tu ne fais AUCUN appel réseau : ces fichiers sont déjà là ou ils n'y sont pas.
S'ils manquent, demande-les via l'orchestrateur ; ne tente pas de les obtenir.

Trois règles d'usage :

1. **La datasheet reste l'autorité.** En cas de désaccord entre
   `.agent_reports/pcbparts-*.md` et la fiche composant issue de la datasheet,
   c'est la datasheet qui gagne, et tu signales la divergence dans ton rapport.
   Le brochage d'un symbole tiers n'a pas valeur de brochage constructeur.
2. **Un modèle importé exige `VALIDATION_VISUELLE_REQUISE`.** Il n'a pas été
   comparé au plan de pose recommandé par le fabricant. Ne rends jamais
   `APPROUVE` sur une carte qui en contient sans le signaler.
3. **Le prix et le type de librairie sont des informations de conception**, pas
   du décor : un composant `extended` coûte 3 $ de frais fixes chez JLCPCB.
   Quand un équivalent `basic` existe à spécifications égales, mentionne-le —
   sans le substituer de ta propre initiative.

## 8. Checklist ERC (à vérifier systématiquement)

1. Chaque circuit intégré a-t-il ses condensateurs de découplage, aux valeurs
   recommandées par sa datasheet ?
2. Les bus I2C ont-ils leurs résistances de pull-up ? Les lignes SPI leurs
   pull-up/pull-down là où c'est requis ?
3. Les broches `RESET`, `EN`, `CS`, `BOOT` sont-elles fixées (pull-up ou
   pull-down) et non flottantes ?
4. Les masses analogique et numérique (`AGND` / `DGND`) sont-elles reliées
   proprement, au bon endroit, si le circuit les distingue ?
5. Y a-t-il des courts-circuits, ou des broches d'alimentation non connectées ?
6. Chaque net a-t-il au moins deux connexions ? Un net à une seule broche est
   soit un oubli, soit un `NC` non déclaré.
