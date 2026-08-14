#!/usr/bin/env python3
"""
Verificateur de script CadQuery, hors cq-editor.

Un script CadQuery se termine par show_object(), qui n'existe que dans
cq-editor : le script n'est donc pas executable tel quel en ligne de commande.
Ce runner fournit un show_object de substitution, execute le script, et rapporte
les erreurs reelles ainsi que les mesures geometriques du resultat.

C'est ce qui transforme la "verification mentale" du reviewer en verification
reelle : une boite englobante eloignee des cotes attendues ou un volume nul
revelent une erreur qu'aucune relecture ne voit.

Usage :
    python .agents/scripts/cq_check.py pieces/boitier.py
    python .agents/scripts/cq_check.py pieces/boitier.py --attendu 120x60x40

Codes de retour : 0 tout va bien, 1 erreur d'execution, 2 erreur d'usage,
3 CadQuery absent, 4 ecart avec les dimensions attendues.
"""

import argparse
import os
import runpy
import sys
import traceback

objets_captures = []


def show_object(obj, name=None, options=None, **kwargs):
    """Substitut de la fonction de cq-editor : on capture au lieu d'afficher."""
    objets_captures.append((name, obj))


def debug(obj, name=None, **kwargs):
    objets_captures.append((name or "debug", obj))


def mesurer(obj):
    """Retourne (bbox, volume, nb_solides) pour un Workplane, Shape ou Assembly."""
    forme = None
    for attr in ("val", "toCompound"):
        if hasattr(obj, attr):
            try:
                forme = getattr(obj, attr)()
                break
            except Exception:
                continue
    if forme is None:
        forme = obj

    infos = {}
    try:
        bb = forme.BoundingBox()
        infos["bbox"] = (bb.xlen, bb.ylen, bb.zlen)
        infos["coins"] = ((bb.xmin, bb.ymin, bb.zmin), (bb.xmax, bb.ymax, bb.zmax))
    except Exception:
        infos["bbox"] = None
    try:
        infos["volume"] = forme.Volume()
    except Exception:
        infos["volume"] = None
    try:
        infos["solides"] = len(forme.Solids())
    except Exception:
        infos["solides"] = None
    return infos


def main():
    ap = argparse.ArgumentParser(description="Verifie un script CadQuery.")
    ap.add_argument("script")
    ap.add_argument(
        "--attendu",
        help="dimensions attendues 'LxPxH' en mm, verifiees a 2%% pres",
    )
    args = ap.parse_args()

    if not os.path.isfile(args.script):
        print("Fichier introuvable : " + args.script, file=sys.stderr)
        return 2

    dossier = os.path.dirname(os.path.abspath(args.script)) or "."
    racine = os.path.abspath(".")
    for chemin in (dossier, racine):
        if chemin not in sys.path:
            sys.path.insert(0, chemin)

    try:
        import cadquery  # noqa: F401
    except ImportError:
        print(
            "CadQuery n'est pas installe dans cet environnement.\n"
            "Installation : pip install cadquery",
            file=sys.stderr,
        )
        return 3

    # On expose show_object/debug au script, comme le ferait cq-editor.
    import builtins

    builtins.show_object = show_object
    builtins.debug = debug

    print("== Execution de " + args.script)
    try:
        runpy.run_path(args.script, run_name="__cq_check__")
    except Exception:
        print("\n== ECHEC : le script leve une exception\n", file=sys.stderr)
        traceback.print_exc()
        return 1

    if not objets_captures:
        print(
            "\n== ECHEC : aucun show_object() n'a ete appele.\n"
            "Un script CadQuery doit se terminer par show_object(...).",
            file=sys.stderr,
        )
        return 1

    print("\n== {} objet(s) affiche(s)".format(len(objets_captures)))
    premier = None
    for i, (nom, obj) in enumerate(objets_captures, 1):
        infos = mesurer(obj)
        if premier is None:
            premier = infos
        etiquette = nom or "objet_{}".format(i)
        print("\n[{}] {}".format(i, etiquette))
        if infos["bbox"]:
            lx, ly, lz = infos["bbox"]
            print("   boite englobante : {:.3f} x {:.3f} x {:.3f} mm".format(lx, ly, lz))
            (xm, ym, zm), (xM, yM, zM) = infos["coins"]
            print(
                "   etendue          : X[{:.3f} .. {:.3f}]  Y[{:.3f} .. {:.3f}]"
                "  Z[{:.3f} .. {:.3f}]".format(xm, xM, ym, yM, zm, zM)
            )
            if abs(zm) > 0.001:
                print(
                    "   ATTENTION : la base n'est pas a Z=0 (Zmin={:.3f}). "
                    "Verifier centered=(True, True, False).".format(zm)
                )
        else:
            print("   boite englobante : non mesurable")
        if infos["volume"] is not None:
            print("   volume           : {:.3f} mm3".format(infos["volume"]))
            if infos["volume"] <= 0.001:
                print("   ATTENTION : volume nul ou negatif, geometrie vide.")
        if infos["solides"] is not None:
            print("   solides          : {}".format(infos["solides"]))
            if infos["solides"] == 0:
                print("   ATTENTION : aucun solide, une soustraction a tout mange.")

    if args.attendu:
        try:
            attendu = [float(v) for v in args.attendu.lower().replace("*", "x").split("x")]
        except ValueError:
            print("\n--attendu mal forme, attendu 'LxPxH'.", file=sys.stderr)
            return 2
        if len(attendu) != 3 or not premier or not premier["bbox"]:
            print("\nComparaison impossible.", file=sys.stderr)
            return 2
        ecarts = []
        for axe, mesure, cible in zip("XYZ", premier["bbox"], attendu):
            if cible and abs(mesure - cible) / cible > 0.02:
                ecarts.append(
                    "{} : mesure {:.3f} mm, attendu {:.3f} mm".format(axe, mesure, cible)
                )
        if ecarts:
            print("\n== ECART avec les dimensions attendues", file=sys.stderr)
            for e in ecarts:
                print("   " + e, file=sys.stderr)
            return 4
        print("\n== Dimensions conformes aux attentes (a 2% pres)")

    print("\n== OK : le script s'execute et produit de la geometrie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
