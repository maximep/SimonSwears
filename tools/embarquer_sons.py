#!/usr/bin/env python3
"""
Fabrique les paquets de sons chargeables par web/simon-swears.html.

Un paquet par langue : web/sons/<code>.js, qui pose les MP3 en data: URI dans
window.SIMON_SONS. Le jeu les charge en injectant une balise <script>, et non
par fetch() : c'est le seul moyen de rester utilisable depuis file://, où toute
requête XHR est refusée pour cause d'origine opaque. Aucun build, aucun serveur,
on ouvre le fichier et ça marche — la contrainte du projet.

Les paquets sont des dérivés des enregistrements d'origine : ils ne sont pas
commités, voir la section Droits de CLAUDE.md. `--tout` les régénère depuis
assets/.

Usage :
    python3 embarquer_sons.py --sons out --out web/sons
    python3 embarquer_sons.py --tout          # extrait puis embarque
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys

LANGUES = [
    ("en",  "English"),      ("fr",  "Français"),
    ("cfr", "Québécois"),    ("de",  "Deutsch"),
    ("it",  "Italiano"),     ("nl",  "Nederlands"),
    ("pt",  "Português"),    ("rs",  "Русский"),
    ("jp",  "日本語"),        ("tk",  "Türkçe"),
    ("hb",  "עברית"),        ("n",   "Norsk"),
]
NOMS = dict(LANGUES)
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)


def paquet(dossier_langue, code):
    """{slot: data URI} pour une langue."""
    sons = {}
    for f in sorted(os.listdir(dossier_langue)):
        if not f.endswith(".mp3"):
            continue
        with open(os.path.join(dossier_langue, f), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        sons[f[:-4]] = "data:audio/mpeg;base64," + b64
    return sons


def ecrire(sons, code, dest):
    """Écrit web/sons/<code>.js. JSON compact, aucune dépendance à l'exécution."""
    corps = json.dumps(sons, ensure_ascii=False, separators=(",", ":"))
    js = (
        "/* Simon Swears — sons d'origine, langue « %s ».\n"
        "   Généré par tools/embarquer_sons.py depuis assets/. Ne pas éditer.\n"
        "   %d son(s). Droits : Joe Tree / Rocket Visuals Limited. */\n"
        "window.SIMON_SONS = window.SIMON_SONS || {};\n"
        "window.SIMON_SONS[%s] = %s;\n"
    ) % (NOMS.get(code, code), len(sons), json.dumps(code), corps)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(js)
    return len(js.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sons", default=os.path.join(RACINE, "out"),
                    metavar="DOSSIER", help="sortie de extraire_sons.py")
    ap.add_argument("--out", default=os.path.join(RACINE, "web", "sons"),
                    metavar="DOSSIER")
    ap.add_argument("--tout", action="store_true",
                    help="extraire d'abord les sons depuis assets/")
    args = ap.parse_args()

    if args.tout:
        dcrs = [os.path.join(RACINE, "assets", "simonswears%s.dcr"
                             % ("" if c == "en" else "-" + c))
                for c, _ in LANGUES]
        manquants = [d for d in dcrs if not os.path.exists(d)]
        if manquants:
            print("films absents : %s\nLancer d'abord tools/fetch_dcr.py."
                  % ", ".join(os.path.basename(m) for m in manquants),
                  file=sys.stderr)
            return 2
        subprocess.check_call(
            [sys.executable, os.path.join(ICI, "extraire_sons.py")] + dcrs
            + ["--out", args.sons, "--par-langue"],
            stdout=subprocess.DEVNULL)

    if not os.path.isdir(args.sons):
        print("dossier de sons introuvable : %s" % args.sons, file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)

    index, total = [], 0
    for code, libelle in LANGUES:
        d = os.path.join(args.sons, code)
        if not os.path.isdir(d):
            print("%-4s %-12s → absent, ignoré" % (code, libelle))
            continue
        sons = paquet(d, code)
        if not sons:
            print("%-4s %-12s → aucun mp3, ignoré" % (code, libelle))
            continue
        n = ecrire(sons, code, os.path.join(args.out, code + ".js"))
        total += n
        index.append({"code": code, "libelle": libelle, "sons": sorted(sons)})
        print("%-4s %-12s → %s/%s.js  %2d son(s)  %6.0f Ko"
              % (code, libelle, os.path.basename(args.out), code,
                 len(sons), n / 1024.0))

    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("\n%d paquet(s), %.1f Mo au total." % (len(index), total / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
