#!/usr/bin/env python3
"""
Recherche d'empreintes et de symboles dans les librairies KiCad installees.

Remplace l'outil maison 'search_kicad_footprint' : Antigravity n'a pas d'outil
dedie, donc on passe par run_command sur ce script.

Deux modes d'usage :

1. INDEXATION (une fois, puis a chaque mise a jour de KiCad)
       python .agents/scripts/kicad_search.py --index
   Ecrit .agents/cache/kicad_index.txt DANS le workspace. Les librairies KiCad
   vivent hors du dossier de travail : une fois indexees, les agents cherchent
   dans ce fichier local avec grep_search, sans sortir du workspace et sans
   declencher de demande de permission.

2. RECHERCHE
       python .agents/scripts/kicad_search.py footprint "SOIC-8"
       python .agents/scripts/kicad_search.py symbol "ESP32-C3"
   Utilise l'index s'il existe (rapide), sinon parcourt les librairies.
   Ajouter --no-index pour forcer le parcours direct.

Sortie : une ligne par resultat, au format 'Librairie:Nom', qui est exactement
la forme attendue dans un script SKiDL. Code de retour 1 si aucun resultat,
pour que l'agent sache qu'il doit chercher un synonyme.
"""

import argparse
import os
import re
import sys

CHEMIN_INDEX = os.path.join(".agents", "cache", "kicad_index.txt")

# Les sous-unites d'un symbole KiCad s'appellent "<NOM>_<unite>_<variante>".
# C'est ce suffixe numerique qui les distingue d'un vrai composant, PAS le
# nombre de underscores : "R_Pack04_Split" ou "ESP32_WROOM_32" sont de vrais
# symboles.
MOTIF_SOUS_UNITE = re.compile(r"_\d+_\d+$")

# Versions de KiCad cherchees, de la plus recente a la plus ancienne. Le kit
# vise KiCad 8 mais les installations en 9 sont courantes : on ne code plus une
# seule version en dur.
VERSIONS_KICAD = ("10.0", "9.0", "8.0", "7.0")

# Variables d'environnement KiCad, toutes versions. L'outil graphique peut
# ecrire l'une ou l'autre selon la version detectee.
VARS_EMPREINTES = (
    "KICAD10_FOOTPRINT_DIR", "KICAD9_FOOTPRINT_DIR", "KICAD8_FOOTPRINT_DIR",
    "KICAD7_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR",
)
VARS_SYMBOLES = (
    "KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR", "KICAD8_SYMBOL_DIR",
    "KICAD7_SYMBOL_DIR", "KICAD_SYMBOL_DIR",
)


def _racines(sous_dossier, variables, locales):
    """Construit la liste des emplacements a fouiller, projet d'abord."""
    racines = list(locales)
    for var in variables:
        if os.environ.get(var):
            racines.append(os.environ[var])
    racines += [
        "/usr/share/kicad/" + sous_dossier,
        "/usr/local/share/kicad/" + sous_dossier,
        "/Applications/KiCad/KiCad.app/Contents/SharedSupport/" + sous_dossier,
    ]
    for v in VERSIONS_KICAD:
        racines += [
            "C:/Program Files/KiCad/{}/share/kicad/{}".format(v, sous_dossier),
            "C:/Program Files (x86)/KiCad/{}/share/kicad/{}".format(v, sous_dossier),
            os.path.expanduser("~/Documents/KiCad/{}/{}".format(v, sous_dossier)),
            os.path.expanduser("~/.local/share/kicad/{}/{}".format(v, sous_dossier)),
        ]
    return racines


RACINES_EMPREINTES = _racines(
    "footprints", VARS_EMPREINTES, ["footprints.pretty", "kicad_libs"]
)
RACINES_SYMBOLES = _racines("symbols", VARS_SYMBOLES, ["kicad_libs"])


def racines_existantes(racines):
    vues, sortie = set(), []
    for r in racines:
        chemin = os.path.abspath(r)
        if chemin not in vues and os.path.isdir(chemin):
            vues.add(chemin)
            sortie.append(chemin)
    return sortie


def chercher_empreintes(motifs, maximum):
    resultats = []
    for racine in racines_existantes(RACINES_EMPREINTES):
        for dossier, _sous, fichiers in os.walk(racine):
            nom_lib = os.path.basename(dossier)
            if nom_lib.endswith(".pretty"):
                nom_lib = nom_lib[: -len(".pretty")]
            for f in fichiers:
                if not f.endswith(".kicad_mod"):
                    continue
                nom = f[: -len(".kicad_mod")]
                cible = (nom_lib + ":" + nom).lower()
                if all(m in cible for m in motifs):
                    resultats.append("{}:{}".format(nom_lib, nom))
                    if len(resultats) >= maximum:
                        return resultats
    return resultats


def chercher_symboles(motifs, maximum):
    """Un .kicad_sym contient plusieurs symboles : on lit les entetes (symbol "Nom")."""
    resultats = []
    for racine in racines_existantes(RACINES_SYMBOLES):
        for dossier, _sous, fichiers in os.walk(racine):
            for f in fichiers:
                if not f.endswith(".kicad_sym"):
                    continue
                nom_lib = f[: -len(".kicad_sym")]
                chemin = os.path.join(dossier, f)
                try:
                    with open(chemin, encoding="utf-8", errors="ignore") as fh:
                        for ligne in fh:
                            depouille = ligne.strip()
                            if not depouille.startswith('(symbol "'):
                                continue
                            nom = depouille.split('"')[1]
                            if MOTIF_SOUS_UNITE.search(nom):
                                continue  # sous-unite de symbole, pas un composant
                            cible = (nom_lib + ":" + nom).lower()
                            if all(m in cible for m in motifs):
                                entree = "{}:{}".format(nom_lib, nom)
                                if entree not in resultats:
                                    resultats.append(entree)
                                if len(resultats) >= maximum:
                                    return resultats
                except OSError:
                    continue
    return resultats


def construire_index():
    """Ecrit l'index complet dans le workspace. Retourne (nb_empreintes, nb_symboles)."""
    empreintes = chercher_empreintes([""], maximum=10**9)
    symboles = chercher_symboles([""], maximum=10**9)
    os.makedirs(os.path.dirname(CHEMIN_INDEX), exist_ok=True)
    with open(CHEMIN_INDEX, "w", encoding="utf-8") as fh:
        fh.write("# Index des librairies KiCad, genere par kicad_search.py --index\n")
        fh.write("# Une ligne par entree : type<TAB>Librairie:Nom\n")
        for e in sorted(set(empreintes)):
            fh.write("footprint\t{}\n".format(e))
        for s in sorted(set(symboles)):
            fh.write("symbol\t{}\n".format(s))
    return len(set(empreintes)), len(set(symboles))


def chercher_dans_index(type_cible, motifs, maximum):
    """Cherche dans l'index local. Retourne None si l'index n'existe pas."""
    if not os.path.isfile(CHEMIN_INDEX):
        return None
    resultats = []
    with open(CHEMIN_INDEX, encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            type_entree, valeur = ligne.rstrip("\n").split("\t", 1)
            if type_entree != type_cible:
                continue
            if all(m in valeur.lower() for m in motifs):
                resultats.append(valeur)
                if len(resultats) >= maximum:
                    break
    return resultats


def main():
    ap = argparse.ArgumentParser(description="Recherche dans les librairies KiCad.")
    ap.add_argument(
        "type", nargs="?", choices=["footprint", "symbol"], help="type recherche"
    )
    ap.add_argument("motif", nargs="?", help="mot-cle, ou plusieurs separes par des espaces")
    ap.add_argument("--index", action="store_true", help="(re)construit l'index local")
    ap.add_argument("--no-index", action="store_true", help="ignore l'index local")
    ap.add_argument("--max", type=int, default=25, dest="maximum")
    args = ap.parse_args()

    if args.index:
        if not racines_existantes(RACINES_EMPREINTES + RACINES_SYMBOLES):
            print(message_aucune_librairie("footprint"), file=sys.stderr)
            return 3
        nb_e, nb_s = construire_index()
        print(
            "Index ecrit dans {} : {} empreintes, {} symboles.".format(
                CHEMIN_INDEX, nb_e, nb_s
            )
        )
        if nb_e == 0 and nb_s == 0:
            print(
                "Index vide : aucune librairie trouvee. Verifier l'installation "
                "de KiCad, ou definir KICAD9_FOOTPRINT_DIR et KICAD9_SYMBOL_DIR "
                "(ou les variables KICAD8_* / KICAD_* equivalentes).",
                file=sys.stderr,
            )
            return 3
        return 0

    if not args.type or not args.motif:
        ap.error("il faut un type et un motif, ou bien --index")

    motifs = [m.lower() for m in args.motif.split() if m]
    if not motifs:
        print("Motif vide.", file=sys.stderr)
        return 2

    source = "index local"
    resultats = None
    if not args.no_index:
        resultats = chercher_dans_index(args.type, motifs, args.maximum)

    # Index absent, ou index present mais muet : on va voir sur le disque. Un
    # index perime (empreintes ajoutees au projet apres sa construction) donnait
    # sinon un « aucun resultat » impossible a distinguer d'une empreinte
    # vraiment inexistante.
    if not resultats:
        if resultats == []:
            source = "parcours direct (rien dans l'index)"
        else:
            source = "parcours direct des librairies"
        racines = racines_existantes(
            RACINES_EMPREINTES if args.type == "footprint" else RACINES_SYMBOLES
        )
        if not racines:
            print(message_aucune_librairie(args.type), file=sys.stderr)
            return 3
        if args.type == "footprint":
            resultats = chercher_empreintes(motifs, args.maximum)
        else:
            resultats = chercher_symboles(motifs, args.maximum)
        if resultats and "index" in source:
            print(
                "Trouve hors index : l'index est perime. Reconstruire avec "
                "--index, ou depuis L'Atelier (Reenregistrer l'env. agents).",
                file=sys.stderr,
            )

    if not resultats:
        print(
            "Aucun resultat pour '{}' ({}). Essayer un synonyme ou un boitier "
            "generique avant de creer l'empreinte.".format(args.motif, source),
            file=sys.stderr,
        )
        return 1

    for r in sorted(set(resultats)):
        print(r)
    print("({} resultats, source : {})".format(len(set(resultats)), source), file=sys.stderr)
    if len(resultats) >= args.maximum:
        print("... (tronque a {} resultats)".format(args.maximum), file=sys.stderr)
    return 0


def message_aucune_librairie(type_cible):
    racines = RACINES_EMPREINTES if type_cible == "footprint" else RACINES_SYMBOLES
    return (
        "Aucune librairie KiCad trouvee sur cette machine.\n"
        "Emplacements testes :\n  "
        + "\n  ".join(racines)
        + "\nSi KiCad est installe ailleurs, definir KICAD9_FOOTPRINT_DIR / "
        "KICAD9_SYMBOL_DIR (ou la variable KICAD8_* correspondante), ou ajouter "
        "le dossier au workspace avec --add-dir."
    )


if __name__ == "__main__":
    sys.exit(main())
