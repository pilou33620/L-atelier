#!/usr/bin/env python3
"""
Execute un script du projet avec l'environnement enregistre par L'Atelier.

Deux problemes a resoudre, et c'est pourquoi ce wrapper existe :

1. Les variables d'environnement KiCad sont definies dans le processus de
   l'outil graphique. Un agent lance ailleurs ne les voit pas, et SKiDL echoue
   sur une librairie de symboles introuvable. On relit .agents/cache/env.json et
   on les reinjecte.

2. SKiDL nomme ses fichiers de sortie (.erc, .log, _sklib.py) d'apres le script
   de PLUS HAUT NIVEAU de la pile d'appels. Executer le script cible depuis ce
   wrapper avec runpy ou exec laissait donc des fichiers appeles
   « run_projet.erc », « run_projet.log » a la racine du projet. On lance donc un
   VRAI sous-processus : le script cible redevient le script de plus haut niveau,
   et ses sorties portent son nom.

Les sous-produits SKiDL sont ensuite ranges a cote du script, dans circuits/.

    python .agents/scripts/run_projet.py circuits/carte-capteur.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CONFIG = RACINE / ".agents" / "cache" / "env.json"

# Sous-produits que SKiDL depose dans le repertoire courant, nommes d'apres le
# script. Le netlist n'y figure pas : le script doit le placer lui-meme avec
# generate_netlist(file_=...).
SUFFIXES = (".erc", ".log", "_sklib.py")


def environnement():
    env = dict(os.environ)
    if not CONFIG.is_file():
        print(
            "Aucun .agents/cache/env.json : execution avec l'environnement brut. "
            "Si SKiDL ne trouve pas ses librairies, relancer la preparation du "
            "projet depuis L'Atelier.",
            file=sys.stderr,
        )
        return env
    try:
        for cle, valeur in json.loads(CONFIG.read_text("utf-8")).items():
            env.setdefault(cle, str(valeur))
    except (ValueError, OSError) as err:
        print("env.json illisible : {}".format(err), file=sys.stderr)
    return env


def ranger(script):
    """Deplace les sous-produits SKiDL a cote du script."""
    base = script.stem
    deplaces = []
    for suffixe in SUFFIXES:
        source = RACINE / (base + suffixe)
        if not source.is_file():
            continue
        cible = script.parent / source.name
        if source.resolve() == cible.resolve():
            continue
        try:
            shutil.move(str(source), str(cible))
            deplaces.append(cible.relative_to(RACINE).as_posix())
        except (OSError, shutil.Error):
            pass
    if deplaces:
        print("Sous-produits ranges : {}".format(", ".join(deplaces)),
              file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("usage : run_projet.py <script.py> [args...]", file=sys.stderr)
        return 2

    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = RACINE / script
    if not script.is_file():
        print("Script introuvable : {}".format(sys.argv[1]), file=sys.stderr)
        return 2

    # Repertoire courant = racine du projet, pour que les chemins relatifs du
    # script (kicad_libs/, footprints.pretty/) restent valides.
    processus = subprocess.run(
        [sys.executable, str(script)] + sys.argv[2:],
        cwd=str(RACINE), env=environnement(),
    )
    ranger(script)
    return processus.returncode


if __name__ == "__main__":
    sys.exit(main())
