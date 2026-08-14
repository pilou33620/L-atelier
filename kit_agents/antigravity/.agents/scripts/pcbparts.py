"""
Client pcbparts.dev pour « L'Atelier » — recherche, prix, modèles KiCad.

pcbparts.dev est un serveur MCP public (https://pcbparts.dev/mcp, HTTP
streamable, sans authentification, 100 requêtes/minute). Il agrège JLCPCB,
Mouser, DigiKey, SamacSys et une base de cartes de référence open source.

Ce module ne fait qu'une chose : parler à ce serveur depuis L'ATELIER, et
déposer le résultat dans le projet sous forme de fichiers et de rapports. Les
agents ne sortent jamais sur le réseau ; ils lisent ce qui a été déposé. C'est
la même règle que pour l'index KiCad et les datasheets, et c'est ce qui garde un
projet reproductible hors ligne et auditable.

Outils utilisés ici :

    cse_search      modèles ECAD disponibles pour une référence (SamacSys)
    cse_get_kicad   téléchargement du symbole et de l'empreinte KiCad
    jlc_get_part    prix par palier, stock, code LCSC, type de librairie
    jlc_get_pinout  brochage extrait des symboles EasyEDA
    board_search    cartes open source utilisant un circuit intégré donné
    get_design_rules  règles de conception par thème

Le format de réponse de `cse_get_kicad` n'est pas documenté publiquement. Plutôt
que de le supposer, `extraire_fichiers()` inspecte la réponse et reconnaît les
trois formes plausibles : contenu de fichier en clair, contenu encodé en base64,
ou URL de téléchargement. Si aucune ne correspond, la structure brute est
retournée pour diagnostic au lieu d'échouer en silence.

Utilisable en ligne de commande pour vérifier le service :

    python pcbparts.py outils
    python pcbparts.py chercher LM358
    python pcbparts.py installer LM358 --projet /chemin/du/projet
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

URL_MCP = "https://pcbparts.dev/mcp"
DELAI = 45

EXTENSIONS_KICAD = (".kicad_sym", ".kicad_mod", ".lib", ".dcm", ".step", ".wrl")


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def _requete(charge, url, timeout):
    donnees = json.dumps(charge).encode("utf-8")
    entetes = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    requete = urllib.request.Request(url, data=donnees, headers=entetes,
                                     method="POST")
    contexte = ssl.create_default_context()
    with urllib.request.urlopen(requete, timeout=timeout,
                                context=contexte) as reponse:
        return reponse.read().decode("utf-8", errors="replace")


def _messages(brut):
    """Extrait les objets JSON-RPC, que la réponse soit du SSE ou du JSON pur.

    Le transport « streamable HTTP » du MCP peut répondre en Server-Sent
    Events (lignes `data: {...}`) ou en JSON direct selon le serveur et la
    requête. On accepte les deux.
    """
    trouves = []
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if ligne.startswith("data:"):
            ligne = ligne[5:].strip()
        if not ligne.startswith("{"):
            continue
        try:
            trouves.append(json.loads(ligne))
        except ValueError:
            continue
    if not trouves:
        try:
            trouves.append(json.loads(brut))
        except ValueError:
            pass
    return trouves


def appeler(nom_outil, arguments=None, url=URL_MCP, timeout=DELAI):
    """Appelle un outil MCP. Retourne (True, données) ou (False, message)."""
    charge = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": nom_outil, "arguments": arguments or {}},
    }
    try:
        brut = _requete(charge, url, timeout)
    except urllib.error.HTTPError as err:
        detail = ""
        try:
            detail = err.read().decode("utf-8", errors="replace")[:300]
        except OSError:
            pass
        return False, "pcbparts.dev a répondu {} {}. {}".format(
            err.code, err.reason, detail)
    except (urllib.error.URLError, OSError, ssl.SSLError) as err:
        return False, "Connexion à pcbparts.dev impossible : {}".format(err)

    for message in _messages(brut):
        if "error" in message:
            erreur = message["error"]
            libelle = erreur.get("message", erreur) if isinstance(erreur, dict) \
                else erreur
            return False, "Le serveur a refusé l'appel « {} » : {}".format(
                nom_outil, libelle)
        resultat = message.get("result")
        if resultat is None:
            continue
        if resultat.get("isError"):
            return False, "L'outil « {} » a renvoyé une erreur : {}".format(
                nom_outil, _texte(resultat)[:400])
        return True, resultat

    return False, ("Réponse inattendue de pcbparts.dev (ni JSON-RPC ni SSE "
                   "exploitable). Début : " + brut[:200])


def lister_outils(url=URL_MCP, timeout=DELAI):
    """Renvoie (True, [(nom, description)]) — utile pour vérifier le service."""
    charge = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        brut = _requete(charge, url, timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as err:
        return False, "Connexion à pcbparts.dev impossible : {}".format(err)
    for message in _messages(brut):
        outils = (message.get("result") or {}).get("tools")
        if outils:
            return True, [(o.get("name", "?"), o.get("description", ""))
                          for o in outils]
    return False, "Le serveur n'a pas renvoyé de liste d'outils."


# --------------------------------------------------------------------------
# Lecture des réponses
# --------------------------------------------------------------------------


def _texte(resultat):
    """Concatène les blocs texte d'un résultat MCP."""
    morceaux = []
    for bloc in resultat.get("content") or []:
        if isinstance(bloc, dict) and bloc.get("type") == "text":
            morceaux.append(bloc.get("text", ""))
    return "\n".join(morceaux)


def donnees(resultat):
    """Renvoie la donnée structurée d'un résultat, JSON du texte à défaut."""
    if isinstance(resultat, dict):
        if resultat.get("structuredContent") is not None:
            return resultat["structuredContent"]
        texte = _texte(resultat)
        if texte.strip().startswith(("{", "[")):
            try:
                return json.loads(texte)
            except ValueError:
                pass
        return texte
    return resultat


# Clés du protocole MCP : elles ne nomment pas le fichier, elles nomment le
# champ qui le transporte. Il faut alors lire le nom dans le contenu lui-même.
CLES_GENERIQUES = {"text", "content", "blob", "data", "value", "result", ""}


def _nom_plausible(cle, contenu):
    """Détermine le nom du fichier : la clé si elle en est un, sinon le contenu."""
    if cle and cle.endswith(EXTENSIONS_KICAD):
        return cle

    debut = contenu.lstrip()
    interne = re.match(r'\((?:kicad_symbol_lib|footprint|module)\b', debut)
    nom_interne = None
    if interne:
        trouve = re.search(r'\((?:symbol|footprint|module)\s+"([^"]+)"', debut)
        if trouve:
            nom_interne = trouve.group(1)

    if cle.lower() in CLES_GENERIQUES or cle.isdigit():
        base = nom_interne or "modele"
    else:
        base = cle
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "modele"

    if debut.startswith("(kicad_symbol_lib") or "(symbol " in debut[:200]:
        return base + ".kicad_sym"
    if debut.startswith(("(footprint", "(module")):
        return base + ".kicad_mod"
    return base


def _telecharger(url, timeout=DELAI):
    try:
        with urllib.request.urlopen(url, timeout=timeout,
                                    context=ssl.create_default_context()) as rep:
            return rep.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def extraire_fichiers(resultat, timeout=DELAI):
    """Extrait {nom: contenu} d'une réponse, quelle que soit sa forme.

    Le schéma de `cse_get_kicad` n'étant pas documenté, on reconnaît :
      - un contenu de fichier en clair (texte commençant par une s-expression) ;
      - un contenu encodé en base64 (bloc `resource`/`blob` du MCP) ;
      - une URL de téléchargement, qui est alors récupérée.
    Retourne aussi la liste des formes NON reconnues, pour diagnostic.
    """
    fichiers = {}
    inconnus = []

    def ajouter(nom, contenu):
        if isinstance(contenu, bytes):
            contenu = contenu.decode("utf-8", errors="replace")
        contenu = contenu.strip()
        if not contenu:
            return
        fichiers[_nom_plausible(nom, contenu)] = contenu

    def visiter(noeud, cle=""):
        if isinstance(noeud, dict):
            # Bloc resource du MCP : text ou blob base64
            if noeud.get("type") in ("resource", "resource_link") or \
                    "uri" in noeud or "blob" in noeud:
                interne = noeud.get("resource", noeud)
                nom = os.path.basename(
                    str(interne.get("name") or interne.get("uri") or cle))
                if interne.get("text"):
                    ajouter(nom, interne["text"])
                    return
                if interne.get("blob"):
                    try:
                        ajouter(nom, base64.b64decode(interne["blob"]))
                        return
                    except (ValueError, TypeError):
                        pass
                uri = str(interne.get("uri") or "")
                if uri.startswith(("http://", "https://")):
                    charge = _telecharger(uri, timeout)
                    if charge is not None:
                        ajouter(nom, charge)
                        return
                inconnus.append(noeud)
                return
            for sous_cle, valeur in noeud.items():
                visiter(valeur, sous_cle)
            return

        if isinstance(noeud, list):
            for element in noeud:
                visiter(element, cle)
            return

        if isinstance(noeud, str):
            depouille = noeud.lstrip()
            if depouille.startswith(("(kicad_symbol_lib", "(footprint",
                                     "(module")):
                ajouter(cle, noeud)
            elif re.match(r"^https?://\S+$", depouille) and \
                    depouille.endswith(EXTENSIONS_KICAD):
                charge = _telecharger(depouille, timeout)
                if charge is not None:
                    ajouter(os.path.basename(depouille), charge)
                else:
                    inconnus.append(depouille)

    # On parcourt la réponse BRUTE (blocs `content`, ressources base64,
    # `structuredContent`) puis, en plus, la donnée structurée décodée : selon
    # la forme, le contenu des fichiers se trouve dans l'une ou dans l'autre.
    visiter(resultat)
    decode = donnees(resultat)
    if isinstance(decode, (dict, list)):
        visiter(decode)
    return fichiers, inconnus


# --------------------------------------------------------------------------
# Opérations de haut niveau
# --------------------------------------------------------------------------


def chercher_modeles(reference, url=URL_MCP, timeout=DELAI):
    return appeler("cse_search", {"query": reference}, url, timeout)


def fiche_composant(reference, url=URL_MCP, timeout=DELAI):
    return appeler("jlc_get_part", {"query": reference}, url, timeout)


def brochage(reference, url=URL_MCP, timeout=DELAI):
    return appeler("jlc_get_pinout", {"query": reference}, url, timeout)


def modeles_kicad(reference, url=URL_MCP, timeout=DELAI):
    return appeler("cse_get_kicad", {"query": reference}, url, timeout)


def _slug(texte):
    return re.sub(r"[^a-z0-9]+", "-", str(texte).lower()).strip("-") or "piece"


def installer(racine_projet, reference, url=URL_MCP, timeout=DELAI):
    """Récupère modèles + prix pour une référence et les dépose dans le projet.

    Écrit :
      kicad_libs/<ref>.kicad_sym          symbole, si fourni
      footprints.pretty/<nom>.kicad_mod   empreinte(s), si fournies
      .agent_reports/pcbparts-<ref>.md    prix, stock, provenance

    Retourne (succes, lignes) — `lignes` est prêt à être affiché.
    """
    racine = Path(racine_projet)
    lignes = []
    if not racine.is_dir():
        return False, ["Dossier projet introuvable : {}".format(racine)]

    ok_modeles, brut_modeles = modeles_kicad(reference, url, timeout)
    fichiers, inconnus = ({}, [])
    if ok_modeles:
        fichiers, inconnus = extraire_fichiers(brut_modeles, timeout)
    else:
        lignes.append("Modèles KiCad : {}".format(brut_modeles))

    ecrits = []
    for nom, contenu in sorted(fichiers.items()):
        if nom.endswith(".kicad_sym"):
            cible = racine / "kicad_libs" / nom
        elif nom.endswith(".kicad_mod"):
            cible = racine / "footprints.pretty" / nom
        else:
            cible = racine / "kicad_libs" / nom
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text(contenu, encoding="utf-8")
        except OSError as err:
            lignes.append("Écriture impossible ({}) : {}".format(nom, err))
            continue
        ecrits.append(cible.relative_to(racine).as_posix())

    if ecrits:
        lignes.append("Fichiers déposés : " + ", ".join(ecrits))
    elif ok_modeles:
        lignes.append(
            "Aucun fichier KiCad exploitable dans la réponse. Le format de "
            "cse_get_kicad a peut-être changé ; la structure brute est "
            "consignée dans le rapport pour diagnostic.")

    ok_fiche, brut_fiche = fiche_composant(reference, url, timeout)
    infos = donnees(brut_fiche) if ok_fiche else None
    if not ok_fiche:
        lignes.append("Prix et stock : {}".format(brut_fiche))

    chemin_rapport = _ecrire_rapport(racine, reference, infos, ecrits,
                                     inconnus if not ecrits else [],
                                     brut_modeles if not ecrits else None)
    if chemin_rapport:
        lignes.append("Rapport écrit : " + chemin_rapport)

    return bool(ecrits or infos), lignes


def _valeur(dico, *cles):
    for cle in cles:
        if isinstance(dico, dict) and dico.get(cle) not in (None, ""):
            return dico[cle]
    return None


def _ecrire_rapport(racine, reference, infos, ecrits, inconnus, brut):
    """Écrit .agent_reports/pcbparts-<ref>.md, lisible par les agents."""
    dossier = racine / ".agent_reports"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ""

    premier = infos
    if isinstance(infos, dict):
        for cle in ("results", "parts", "data"):
            if isinstance(infos.get(cle), list) and infos[cle]:
                premier = infos[cle][0]
                break
    if not isinstance(premier, dict):
        premier = {}

    lignes = [
        "# PCBParts — {}".format(reference),
        "",
        "Mission : import de modèles et de tarifs depuis pcbparts.dev",
        "Récupéré le : {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")),
        "",
        "> **Source tierce, pas une datasheet.** Ces données viennent de "
        "pcbparts.dev (JLCPCB / LCSC pour les tarifs, SamacSys pour les "
        "modèles ECAD). En cas de désaccord avec la datasheet du fabricant, "
        "**la datasheet a raison**. Un modèle téléchargé n'a pas été vérifié "
        "contre le plan de pose recommandé : il exige "
        "`VALIDATION_VISUELLE_REQUISE`.",
        "",
        "## Approvisionnement",
        "",
        "| Champ | Valeur |",
        "|---|---|",
    ]
    for etiquette, cles in (
        ("Référence fabricant", ("mpn", "model", "manufacturerPart", "part")),
        ("Fabricant", ("manufacturer", "brand")),
        ("Code LCSC", ("lcsc", "lcscPart", "code")),
        ("Boîtier", ("package", "footprintName")),
        ("Type de librairie", ("library_type", "libraryType", "type")),
        ("Prix unitaire", ("price", "unitPrice")),
        ("Stock", ("stock", "quantity")),
        ("Datasheet", ("datasheet", "datasheetUrl")),
    ):
        valeur = _valeur(premier, *cles)
        if valeur is not None:
            lignes.append("| {} | {} |".format(etiquette, valeur))

    paliers = _valeur(premier, "prices", "priceTiers", "price_tiers")
    if isinstance(paliers, list) and paliers:
        lignes += ["", "## Prix par palier", "", "| Quantité | Prix unitaire |",
                   "|---|---|"]
        for palier in paliers[:12]:
            if isinstance(palier, dict):
                lignes.append("| {} | {} |".format(
                    _valeur(palier, "qty", "quantity", "from") or "?",
                    _valeur(palier, "price", "unitPrice") or "?"))

    specs = _valeur(premier, "specs", "attributes", "specifications")
    if isinstance(specs, dict) and specs:
        lignes += ["", "## Spécifications annoncées", "",
                   "| Spécification | Valeur |", "|---|---|"]
        for cle, valeur in list(specs.items())[:30]:
            lignes.append("| {} | {} |".format(cle, valeur))

    lignes += ["", "## Fichiers déposés dans le projet", ""]
    if ecrits:
        for chemin in ecrits:
            lignes.append("- `{}`".format(chemin))
        lignes += [
            "",
            "Le symbole s'instancie depuis `kicad_libs/`, l'empreinte se "
            "référence sous `footprints:<nom>` — le dossier "
            "`footprints.pretty/` est cherché avant les librairies globales. "
            "Reconstruire l'index KiCad après cet import.",
        ]
    else:
        lignes.append("- aucun")
        if inconnus or brut is not None:
            lignes += [
                "",
                "### Diagnostic (structure non reconnue)",
                "",
                "Aucun contenu de fichier KiCad n'a pu être extrait. Extrait "
                "brut de la réponse, pour adapter l'extraction :",
                "",
                "```json",
                json.dumps(inconnus or brut, indent=2, ensure_ascii=False,
                           default=str)[:3000],
                "```",
            ]

    lignes.append("")
    lignes.append("VERDICT : VALIDATION_VISUELLE_REQUISE")
    lignes.append("")
    lignes.append(
        "Comparer le plan de pose du modèle importé avec celui de la datasheet "
        "avant de router : dimensions de pastilles, pas, pastille thermique. "
        "Un modèle tiers plausible mais faux produit une carte qui se fabrique "
        "sans erreur et ne fonctionne pas.")

    chemin = dossier / "pcbparts-{}.md".format(_slug(reference))
    try:
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError:
        return ""
    return chemin.relative_to(racine).as_posix()


# --------------------------------------------------------------------------
# Ligne de commande
# --------------------------------------------------------------------------


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    action = argv[1]
    url = os.environ.get("PCBPARTS_URL", URL_MCP)

    if action == "outils":
        ok, resultat = lister_outils(url)
        if not ok:
            print(resultat, file=sys.stderr)
            return 1
        for nom, description in resultat:
            print("{:24s} {}".format(nom, (description or "")[:90]))
        return 0

    if len(argv) < 3:
        print("usage : pcbparts.py {outils|disponible|chercher|installer} <reference> "
              "[--projet <dossier>]", file=sys.stderr)
        return 2
    reference = argv[2]

    if action == "disponible":
        ok, resultat = chercher_modeles(reference, url)
        if not ok:
            print(resultat, file=sys.stderr)
            return 1
        charge = donnees(resultat)
        # Une enveloppe non vide qui contient une liste vide reste un « rien
        # trouve » : c'est le cas le plus courant, et le confondre avec un
        # succes enverrait l'agent chercher un modele qui n'existe pas.
        listes = []
        if isinstance(charge, dict):
            for cle in ("results", "parts", "models", "items", "data"):
                if isinstance(charge.get(cle), list):
                    listes.append(charge[cle])
        vide = (not charge
                or (isinstance(charge, list) and not charge)
                or (listes and not any(listes)))
        if vide:
            print("Aucun modele ECAD chez SamacSys pour « {} ».".format(reference),
                  file=sys.stderr)
            return 1
        print(json.dumps(charge, ensure_ascii=False, default=str)[:2000])
        return 0

    if action == "chercher":
        ok, resultat = chercher_modeles(reference, url)
        print(json.dumps(donnees(resultat) if ok else resultat, indent=2,
                         ensure_ascii=False, default=str)[:4000])
        return 0 if ok else 1

    if action == "installer":
        projet = "."
        if "--projet" in argv:
            projet = argv[argv.index("--projet") + 1]
        ok, lignes = installer(projet, reference, url)
        for ligne in lignes:
            print(("  " if ok else "! ") + ligne)
        return 0 if ok else 1

    print("Action inconnue : {}".format(action), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
