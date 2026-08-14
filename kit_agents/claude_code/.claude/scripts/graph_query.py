#!/usr/bin/env python3
"""
Interrogation de graphify-out/graph.json sans le charger dans le contexte.

Un graph.json de projet reel pese plusieurs megaoctets : le lire avec view_file
epuiserait le contexte d'un agent d'un seul coup. Ce script repond a des questions
ciblees et ne sort que quelques lignes.

Le schema exact de graph.json peut varier selon la version de Graphify. Ce script
DETECTE le schema au chargement plutot que de le supposer, et la sous-commande
'schema' affiche ce qu'il a trouve : c'est le premier reflexe si un resultat
parait vide a tort.

Usage :
    python .agents/scripts/graph_query.py stats
    python .agents/scripts/graph_query.py schema
    python .agents/scripts/graph_query.py find "authenticate"
    python .agents/scripts/graph_query.py callers "valider_commande"
    python .agents/scripts/graph_query.py callees "traiter_paiement"
    python .agents/scripts/graph_query.py neighbors "Facture"
    python .agents/scripts/graph_query.py path "api" "base"
    python .agents/scripts/graph_query.py file "src/paiement.py"

Options : --graph <chemin>, --max N
Codes de retour : 0 resultats, 1 aucun resultat, 2 usage, 3 graphe absent ou
schema non reconnu.
"""

import argparse
import json
import os
import sys
from collections import deque

CHEMIN_DEFAUT = os.path.join("graphify-out", "graph.json")

CLES_NOEUDS = ("nodes", "vertices", "entities", "symbols")
CLES_ARETES = ("edges", "links", "relationships", "relations")
CLES_ID = ("id", "name", "label", "key", "qualified_name", "symbol")
CLES_FICHIER = ("file", "path", "filepath", "file_path", "source_file", "location")
CLES_TYPE = ("type", "kind", "category", "node_type")
CLES_SOURCE = ("source", "from", "src", "start", "subject", "tail")
CLES_CIBLE = ("target", "to", "dst", "end", "object", "head")
CLES_RELATION = ("type", "label", "relation", "kind", "edge_type")
CLES_CONFIANCE = ("confidence", "tag", "provenance", "origin")


def premiere_cle(dico, cles):
    for c in cles:
        if isinstance(dico, dict) and c in dico and dico[c] not in (None, ""):
            return c
    return None


def valeur(dico, cles, defaut=""):
    c = premiere_cle(dico, cles)
    v = dico.get(c, defaut) if c else defaut
    if isinstance(v, dict):
        v = v.get("file") or v.get("path") or json.dumps(v, ensure_ascii=False)[:80]
    return v if isinstance(v, str) else str(v)


class Graphe:
    def __init__(self, chemin):
        with open(chemin, encoding="utf-8") as fh:
            brut = json.load(fh)

        # Le graphe peut etre a la racine, ou imbrique sous 'graph' / 'data'.
        self.racine = brut
        if isinstance(brut, dict):
            for enveloppe in ("graph", "data", "result"):
                if enveloppe in brut and isinstance(brut[enveloppe], dict):
                    if any(k in brut[enveloppe] for k in CLES_NOEUDS):
                        self.racine = brut[enveloppe]
                        break

        self.cle_noeuds = premiere_cle(self.racine, CLES_NOEUDS)
        self.cle_aretes = premiere_cle(self.racine, CLES_ARETES)
        if not self.cle_noeuds:
            raise ValueError(
                "Aucune liste de noeuds reconnue. Cles de premier niveau : "
                + ", ".join(sorted(self.racine.keys())[:20])
            )

        noeuds_bruts = self.racine[self.cle_noeuds]
        if isinstance(noeuds_bruts, dict):  # dictionnaire id -> noeud
            noeuds_bruts = [
                dict(n, **{"id": k}) if isinstance(n, dict) else {"id": k}
                for k, n in noeuds_bruts.items()
            ]

        self.noeuds = {}
        for n in noeuds_bruts:
            if not isinstance(n, dict):
                continue
            ident = valeur(n, CLES_ID)
            if not ident:
                continue
            self.noeuds[ident] = {
                "id": ident,
                "fichier": valeur(n, CLES_FICHIER),
                "type": valeur(n, CLES_TYPE),
            }

        self.aretes = []
        self.sortantes = {}
        self.entrantes = {}
        for a in self.racine.get(self.cle_aretes) or []:
            if not isinstance(a, dict):
                continue
            src = valeur(a, CLES_SOURCE)
            dst = valeur(a, CLES_CIBLE)
            if not src or not dst:
                continue
            arete = {
                "source": src,
                "cible": dst,
                "relation": valeur(a, CLES_RELATION, "?"),
                "confiance": valeur(a, CLES_CONFIANCE, "?"),
            }
            self.aretes.append(arete)
            self.sortantes.setdefault(src, []).append(arete)
            self.entrantes.setdefault(dst, []).append(arete)

    def resoudre(self, motif):
        """Trouve les identifiants correspondant a un motif, exact d'abord."""
        if motif in self.noeuds:
            return [motif]
        bas = motif.lower()
        exacts = [i for i in self.noeuds if i.lower() == bas]
        if exacts:
            return exacts
        finaux = [i for i in self.noeuds if i.lower().split(".")[-1] == bas]
        if finaux:
            return finaux
        return [i for i in self.noeuds if bas in i.lower()]

    def decrire(self, ident):
        n = self.noeuds.get(ident)
        if not n:
            return ident
        bouts = [ident]
        if n["type"]:
            bouts.append("[" + n["type"] + "]")
        if n["fichier"]:
            bouts.append("-> " + n["fichier"])
        return " ".join(bouts)

    def chemin(self, depart, arrivee, limite=8):
        """Plus court chemin non oriente entre deux noeuds."""
        if depart == arrivee:
            return [depart]
        vus = {depart}
        file = deque([[depart]])
        while file:
            trajet = file.popleft()
            if len(trajet) > limite:
                continue
            dernier = trajet[-1]
            voisins = [a["cible"] for a in self.sortantes.get(dernier, [])] + [
                a["source"] for a in self.entrantes.get(dernier, [])
            ]
            for v in voisins:
                if v in vus:
                    continue
                if v == arrivee:
                    return trajet + [v]
                vus.add(v)
                file.append(trajet + [v])
        return None


def afficher_aretes(aretes, graphe, maximum, sens):
    if not aretes:
        return 1
    incertaines = 0
    for a in aretes[:maximum]:
        autre = a["source"] if sens == "entrant" else a["cible"]
        marque = ""
        if str(a["confiance"]).upper().startswith("INFER"):
            marque = "   <-- INFERRED, a verifier"
            incertaines += 1
        print(
            "  {:<12} {:<10} {}{}".format(
                a["relation"][:12], a["confiance"][:10], graphe.decrire(autre), marque
            )
        )
    if len(aretes) > maximum:
        print("  ... {} de plus (--max pour en voir davantage)".format(len(aretes) - maximum))
    if incertaines:
        print(
            "\n  {} relation(s) INFERRED : ce sont des hypotheses. Verifier au "
            "grep_search avant d'agir.".format(incertaines)
        )
    return 0


def main():
    ap = argparse.ArgumentParser(description="Interroge le graphe Graphify.")
    ap.add_argument(
        "commande",
        choices=["stats", "schema", "find", "callers", "callees", "neighbors", "path", "file"],
    )
    ap.add_argument("cible", nargs="?")
    ap.add_argument("cible2", nargs="?")
    ap.add_argument("--graph", default=CHEMIN_DEFAUT)
    ap.add_argument("--max", type=int, default=30, dest="maximum")
    args = ap.parse_args()

    if not os.path.isfile(args.graph):
        print(
            "Graphe introuvable : {}\n"
            "Le graphe n'est pas obligatoire : retomber sur grep_search et "
            "find_by_name. Pour le construire, c'est a l'utilisateur de lancer "
            "Graphify sur le projet.".format(args.graph),
            file=sys.stderr,
        )
        return 3

    try:
        g = Graphe(args.graph)
    except (ValueError, json.JSONDecodeError) as err:
        print(
            "Schema de graphe non reconnu : {}\n"
            "Lancer 'graph_query.py schema' pour voir la structure detectee.".format(err),
            file=sys.stderr,
        )
        return 3

    if args.commande == "schema":
        print("Fichier          : {}".format(args.graph))
        print("Cle des noeuds   : {}".format(g.cle_noeuds))
        print("Cle des aretes   : {}".format(g.cle_aretes))
        print("Noeuds charges   : {}".format(len(g.noeuds)))
        print("Aretes chargees  : {}".format(len(g.aretes)))
        exemple = next(iter(g.noeuds.values()), None)
        if exemple:
            print("Exemple de noeud : {}".format(exemple))
        if g.aretes:
            print("Exemple d'arete  : {}".format(g.aretes[0]))
        return 0

    if args.commande == "stats":
        types = {}
        for n in g.noeuds.values():
            types[n["type"] or "?"] = types.get(n["type"] or "?", 0) + 1
        relations = {}
        confiances = {}
        for a in g.aretes:
            relations[a["relation"]] = relations.get(a["relation"], 0) + 1
            confiances[a["confiance"]] = confiances.get(a["confiance"], 0) + 1
        print("{} noeuds, {} aretes".format(len(g.noeuds), len(g.aretes)))
        print("\nTypes de noeuds :")
        for t, c in sorted(types.items(), key=lambda x: -x[1])[:12]:
            print("  {:<24} {}".format(t, c))
        print("\nTypes de relations :")
        for t, c in sorted(relations.items(), key=lambda x: -x[1])[:12]:
            print("  {:<24} {}".format(t, c))
        print("\nConfiance :")
        for t, c in sorted(confiances.items(), key=lambda x: -x[1])[:8]:
            print("  {:<24} {}".format(t, c))
        print("\nLes plus connectes (god nodes) :")
        degres = {
            i: len(g.sortantes.get(i, [])) + len(g.entrantes.get(i, []))
            for i in g.noeuds
        }
        for i, d in sorted(degres.items(), key=lambda x: -x[1])[:10]:
            print("  {:<4} {}".format(d, g.decrire(i)))
        return 0

    if not args.cible:
        ap.error("cette commande demande une cible")

    if args.commande == "file":
        bas = args.cible.lower().replace("\\", "/")
        trouves = [n for n in g.noeuds.values() if bas in n["fichier"].lower().replace("\\", "/")]
        if not trouves:
            print("Aucun noeud dans un fichier contenant '{}'.".format(args.cible), file=sys.stderr)
            return 1
        print("{} noeud(s) dans '{}' :".format(len(trouves), args.cible))
        for n in trouves[: args.maximum]:
            print("  {:<12} {}".format(n["type"][:12], n["id"]))
        if len(trouves) > args.maximum:
            print("  ... {} de plus".format(len(trouves) - args.maximum))
        return 0

    if args.commande == "find":
        trouves = g.resoudre(args.cible)
        if not trouves:
            print("Aucun noeud pour '{}'.".format(args.cible), file=sys.stderr)
            return 1
        print("{} correspondance(s) pour '{}' :".format(len(trouves), args.cible))
        for i in trouves[: args.maximum]:
            d = len(g.sortantes.get(i, [])) + len(g.entrantes.get(i, []))
            print("  ({} liens) {}".format(d, g.decrire(i)))
        if len(trouves) > args.maximum:
            print("  ... {} de plus".format(len(trouves) - args.maximum))
        return 0

    if args.commande == "path":
        if not args.cible2:
            ap.error("path demande deux cibles")
        a = g.resoudre(args.cible)
        b = g.resoudre(args.cible2)
        if not a or not b:
            print("Cible introuvable ({} / {}).".format(bool(a), bool(b)), file=sys.stderr)
            return 1
        trajet = g.chemin(a[0], b[0])
        if not trajet:
            print(
                "Aucun chemin trouve entre '{}' et '{}' (dans la limite de 8 sauts). "
                "Absence de chemin dans le graphe ne prouve pas l'absence de lien "
                "dans le code.".format(a[0], b[0]),
                file=sys.stderr,
            )
            return 1
        print("Chemin ({} sauts) :".format(len(trajet) - 1))
        for etape, ident in enumerate(trajet):
            print("  {}{}".format("  " * etape, g.decrire(ident)))
        return 0

    # callers / callees / neighbors
    trouves = g.resoudre(args.cible)
    if not trouves:
        print("Aucun noeud pour '{}'.".format(args.cible), file=sys.stderr)
        return 1
    if len(trouves) > 1:
        print("Plusieurs correspondances, utilisation de '{}'.".format(trouves[0]), file=sys.stderr)
        print("Autres : {}".format(", ".join(trouves[1:6])), file=sys.stderr)
    ident = trouves[0]
    print(g.decrire(ident))

    if args.commande == "callers":
        entrants = g.entrantes.get(ident, [])
        print("\n{} entrant(s) — ce qui casse si tu modifies ce symbole :".format(len(entrants)))
        return afficher_aretes(entrants, g, args.maximum, "entrant")

    if args.commande == "callees":
        sortants = g.sortantes.get(ident, [])
        print("\n{} sortant(s) — ce dont ce symbole depend :".format(len(sortants)))
        return afficher_aretes(sortants, g, args.maximum, "sortant")

    entrants = g.entrantes.get(ident, [])
    sortants = g.sortantes.get(ident, [])
    print("\n{} entrant(s) :".format(len(entrants)))
    afficher_aretes(entrants, g, args.maximum // 2 or 1, "entrant")
    print("\n{} sortant(s) :".format(len(sortants)))
    afficher_aretes(sortants, g, args.maximum // 2 or 1, "sortant")
    return 0 if (entrants or sortants) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # sortie tronquee par un pipe (| head), ce n'est pas une erreur
        os._exit(0)
    except KeyboardInterrupt:
        os._exit(130)
