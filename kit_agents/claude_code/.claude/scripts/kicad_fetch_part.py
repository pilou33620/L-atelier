#!/usr/bin/env python3
"""
Extrait un symbole des librairies KiCad vers kicad_libs/ du projet.

Le kit impose que le symbole de tout circuit integre existe LOCALEMENT avant
d'etre instancie en SKiDL, pour que le projet reste reproductible et pour qu'un
symbole ne puisse pas etre invente. Ce script est le chainon qui remplit
kicad_libs/ : il recopie un symbole reel, avec ses sous-unites et son symbole
parent s'il en derive.

Usage :

    python .agents/scripts/kicad_fetch_part.py chercher "ESP32-C3-MINI"
    python .agents/scripts/kicad_fetch_part.py copier "RF_Module:ESP32-C3-MINI-1"
    python .agents/scripts/kicad_fetch_part.py copier "Device:C_Small" --nom cond

Le fichier produit est kicad_libs/<nom>.kicad_sym, utilisable directement :

    u1 = Part('kicad_libs/ESP32-C3-MINI-1.kicad_sym', 'ESP32-C3-MINI-1',
              footprint='RF_Module:ESP32-C3-MINI-1')

Codes de sortie : 0 succes, 1 rien trouve, 2 usage, 3 erreur d'ecriture.
"""

import argparse
import os
import re
import sys

DOSSIER_LOCAL = "kicad_libs"

# Reutilise la detection des librairies de kicad_search.py, pour ne pas avoir
# deux listes de chemins a maintenir.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from kicad_search import MOTIF_SOUS_UNITE, RACINES_SYMBOLES
except ImportError:  # pragma: no cover
    print("kicad_search.py doit etre a cote de ce script.", file=sys.stderr)
    sys.exit(2)


def librairies():
    """Toutes les librairies .kicad_sym visibles, dedoublonnees."""
    vues = set()
    trouvees = []
    for racine in RACINES_SYMBOLES:
        racine = os.path.abspath(racine)
        if not os.path.isdir(racine):
            continue
        for dossier, _, fichiers in os.walk(racine):
            for nom in fichiers:
                if not nom.endswith(".kicad_sym"):
                    continue
                chemin = os.path.join(dossier, nom)
                cle = (nom, os.path.getsize(chemin))
                if cle in vues:
                    continue
                vues.add(cle)
                trouvees.append(chemin)
    return trouvees


def _blocs_symboles(texte):
    """Renvoie {nom: (debut, fin)} pour chaque symbole de premier niveau.

    Un decoupage naif sur les parentheses casse des qu'une chaine en contient
    une (les champs de description en sont pleins). On suit donc l'etat
    « dans une chaine » et les echappements.
    """
    blocs = {}
    i = 0
    longueur = len(texte)
    profondeur = 0
    dans_chaine = False
    # Pile des symboles ouverts : (nom, position_debut, profondeur_ouverture)
    ouverts = []

    while i < longueur:
        c = texte[i]

        if dans_chaine:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                dans_chaine = False
            i += 1
            continue

        if c == '"':
            dans_chaine = True
            i += 1
            continue

        if c == "(":
            correspondance = re.match(r'\(symbol\s+"((?:[^"\\]|\\.)*)"', texte[i:])
            profondeur += 1
            if correspondance:
                ouverts.append((correspondance.group(1), i, profondeur))
            i += 1
            continue

        if c == ")":
            if ouverts and ouverts[-1][2] == profondeur:
                nom, debut, _ = ouverts.pop()
                # Seuls les symboles de premier niveau nous interessent : les
                # sous-unites sont deja contenues dans leur bloc parent.
                if not ouverts and not MOTIF_SOUS_UNITE.search(nom):
                    blocs[nom] = (debut, i + 1)
            profondeur -= 1
            i += 1
            continue

        i += 1

    return blocs


def _parent(bloc):
    """Nom du symbole dont celui-ci derive, s'il y en a un."""
    correspondance = re.search(r'\(extends\s+"((?:[^"\\]|\\.)*)"', bloc)
    return correspondance.group(1) if correspondance else None


def chercher(motif, maximum=40):
    """Liste les symboles dont le nom contient le motif (insensible a la casse)."""
    motif = motif.lower()
    resultats = []
    for chemin in librairies():
        librairie = os.path.splitext(os.path.basename(chemin))[0]
        try:
            with open(chemin, "r", encoding="utf-8", errors="ignore") as fh:
                texte = fh.read()
        except OSError:
            continue
        for nom in _blocs_symboles(texte):
            if motif in nom.lower() or motif in "{}:{}".format(librairie, nom).lower():
                resultats.append(("{}:{}".format(librairie, nom), chemin))
                if len(resultats) >= maximum:
                    return resultats
    return resultats


def _localiser(reference):
    """Retrouve (chemin, texte, nom) a partir de 'Librairie:Nom' ou 'Nom'."""
    if ":" in reference:
        librairie_voulue, nom_voulu = reference.split(":", 1)
    else:
        librairie_voulue, nom_voulu = None, reference

    for chemin in librairies():
        librairie = os.path.splitext(os.path.basename(chemin))[0]
        if librairie_voulue and librairie.lower() != librairie_voulue.lower():
            continue
        try:
            with open(chemin, "r", encoding="utf-8", errors="ignore") as fh:
                texte = fh.read()
        except OSError:
            continue
        blocs = _blocs_symboles(texte)
        for nom in blocs:
            if nom.lower() == nom_voulu.lower():
                return chemin, texte, nom, blocs
    return None, None, None, None


def copier(reference, nom_fichier=None, destination=DOSSIER_LOCAL):
    """Ecrit le symbole (et son parent) dans destination/<nom>.kicad_sym."""
    chemin, texte, nom, blocs = _localiser(reference)
    if chemin is None:
        print(
            "Symbole introuvable : {}\n"
            "Cherche d'abord son nom exact :\n"
            "  python .agents/scripts/kicad_fetch_part.py chercher \"{}\"".format(
                reference, reference.split(":")[-1]
            ),
            file=sys.stderr,
        )
        return 1

    # Un symbole derive (extends) est inutilisable sans son parent : on emporte
    # la chaine complete.
    a_ecrire = []
    vus = set()
    file_attente = [nom]
    while file_attente:
        courant = file_attente.pop(0)
        if courant in vus or courant not in blocs:
            continue
        vus.add(courant)
        debut, fin = blocs[courant]
        bloc = texte[debut:fin]
        a_ecrire.append(bloc)
        ascendant = _parent(bloc)
        if ascendant:
            file_attente.append(ascendant)

    manquants = [p for p in (_parent(b) for b in a_ecrire) if p and p not in vus]
    if manquants:
        print(
            "Attention : symbole(s) parent(s) absent(s) de la meme librairie : "
            "{}. Le symbole recopie sera incomplet.".format(", ".join(manquants)),
            file=sys.stderr,
        )

    os.makedirs(destination, exist_ok=True)
    cible = os.path.join(destination, (nom_fichier or nom) + ".kicad_sym")
    contenu = (
        '(kicad_symbol_lib (version 20211014) (generator kicad_fetch_part)\n'
        + "\n".join("  " + b.replace("\n", "\n  ") for b in reversed(a_ecrire))
        + "\n)\n"
    )
    try:
        with open(cible, "w", encoding="utf-8") as fh:
            fh.write(contenu)
    except OSError as err:
        print("Ecriture impossible : {}".format(err), file=sys.stderr)
        return 3

    print("{} recopie depuis {}".format(nom, os.path.basename(chemin)))
    print("  -> {}".format(cible))
    if len(a_ecrire) > 1:
        print("  (avec son symbole parent : {})".format(
            ", ".join(sorted(vus - {nom}))))
    print("\nUtilisation en SKiDL :")
    print("  Part('{}', '{}',".format(cible.replace(os.sep, "/"), nom))
    print("       footprint='<Librairie>:<Empreinte>')")
    print("\nL'empreinte se cherche separement :")
    print('  python .agents/scripts/kicad_search.py footprint "<boitier>"')
    return 0


def main():
    analyseur = argparse.ArgumentParser(
        description="Extrait un symbole KiCad vers kicad_libs/.")
    analyseur.add_argument("action", choices=["chercher", "copier"])
    analyseur.add_argument("reference",
                           help="motif de recherche, ou 'Librairie:Nom' a copier")
    analyseur.add_argument("--nom", default=None,
                           help="nom du fichier produit, sans extension")
    analyseur.add_argument("--dest", default=DOSSIER_LOCAL,
                           help="dossier de destination (defaut : kicad_libs)")
    analyseur.add_argument("--max", type=int, default=40, dest="maximum")
    arguments = analyseur.parse_args()

    if arguments.action == "chercher":
        resultats = chercher(arguments.reference, arguments.maximum)
        if not resultats:
            print("Aucun symbole ne correspond a « {} ».".format(arguments.reference),
                  file=sys.stderr)
            return 1
        for reference, chemin in resultats:
            print("{}\t{}".format(reference, os.path.basename(chemin)))
        print("({} resultats)".format(len(resultats)), file=sys.stderr)
        return 0

    return copier(arguments.reference, arguments.nom, arguments.dest)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        os._exit(0)
