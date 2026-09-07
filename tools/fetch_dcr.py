#!/usr/bin/env python3
"""
Acquisition des films Shockwave de Simon Swears.

Récupère les douze .dcr linguistiques depuis le serveur d'origine, avec repli
sur la Wayback Machine. Chaque fichier est validé avant écriture : un serveur
qui renvoie une page d'erreur en HTTP 200 produit un HTML déguisé en .dcr, et
on refuse ça explicitement plutôt que de le découvrir au parsing.

Usage :
    python3 fetch_dcr.py --list              # ce qui est disponible, sans écrire
    python3 fetch_dcr.py --out assets/       # tout récupérer
    python3 fetch_dcr.py --out assets/ --only fr,de
    python3 fetch_dcr.py --out assets/ --source wayback
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://www.diyjoe.com/simonswears/"

# En-tête de navigateur : le serveur sert normalement, mais autant ne pas
# ressembler à un robot sur une machine qui n'a plus de mainteneur.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Les cibles des gotoNetMovie lues dans les 47 Lscr de loading.dcr.
VERSIONS = [
    ("en",  "simonswears.dcr",     "anglais"),
    ("fr",  "simonswears-fr.dcr",  "français"),
    ("cfr", "simonswears-cfr.dcr", "français canadien"),
    ("de",  "simonswears-de.dcr",  "allemand"),
    ("it",  "simonswears-it.dcr",  "italien"),
    ("nl",  "simonswears-nl.dcr",  "néerlandais"),
    ("pt",  "simonswears-pt.dcr",  "portugais"),
    ("rs",  "simonswears-rs.dcr",  "russe"),
    ("jp",  "simonswears-jp.dcr",  "japonais"),
    ("tk",  "simonswears-tk.dcr",  "turc"),
    ("hb",  "simonswears-hb.dcr",  "hébreu"),
    ("n",   "simonswears-n.dcr",   "norvégien"),
    ("--",  "loading.dcr",         "sélecteur de langue"),
]

# RIFX gros-boutiste, XFIR petit-boutiste (Director sous Windows).
MAGIES = (b"RIFX", b"XFIR")


class Refus(Exception):
    """Le corps téléchargé n'est pas un film Director."""


def valider(blob, url):
    """Vérifie qu'on tient bien un .dcr. Lève Refus avec la raison exacte."""
    if len(blob) < 12:
        raise Refus("%d octets seulement, tronqué ou vide" % len(blob))
    magie = blob[:4]
    if magie not in MAGIES:
        apercu = blob[:64].decode("latin1").replace("\n", " ").strip()
        if magie[:1] == b"<":
            raise Refus("HTML servi en HTTP 200 (page d'erreur ?) : %r" % apercu[:60])
        raise Refus("magie %r inattendue, attendu RIFX ou XFIR : %r"
                    % (magie.decode("latin1"), apercu[:40]))
    codec = blob[8:12]
    if codec not in (b"FGDM", b"FGDC", b"MV93"):
        # Pas bloquant : on signale et on garde, le parser tranchera.
        print("    codec %r inhabituel (ni Afterburner ni MV93)"
              % codec.decode("latin1"), file=sys.stderr)
    return codec.decode("latin1")


def telecharger(url, delai=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=delai) as rep:
        return rep.read(), rep.status


def url_wayback(nom):
    """Snapshot brut le plus récent. Le suffixe id_ évite la barre d'archive."""
    return ("https://web.archive.org/web/2id_/"
            "http://www.diyjoe.com/simonswears/" + nom)


def recuperer(nom, source):
    """Renvoie (blob, url_utilisée, codec). Lève Refus ou URLError."""
    sources = {"origine": [BASE + nom],
               "wayback": [url_wayback(nom)]}.get(
                   source, [BASE + nom, url_wayback(nom)])
    dernier = None
    for url in sources:
        try:
            blob, statut = telecharger(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            dernier = "%s : %s" % (url, e)
            continue
        try:
            codec = valider(blob, url)
        except Refus as e:
            dernier = "%s : %s" % (url, e)
            continue
        return blob, url, codec
    raise Refus(dernier or "aucune source")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", metavar="DOSSIER",
                    help="où écrire les .dcr (sinon : simple sondage)")
    ap.add_argument("--list", action="store_true",
                    help="sonder la disponibilité sans écrire")
    ap.add_argument("--only", metavar="CODES",
                    help="codes langue séparés par des virgules (ex. fr,de,jp)")
    ap.add_argument("--source", choices=["origine", "wayback", "auto"],
                    default="auto", help="où chercher (défaut : auto)")
    ap.add_argument("--force", action="store_true",
                    help="retélécharger même si le fichier existe déjà")
    args = ap.parse_args()

    cibles = VERSIONS
    if args.only:
        voulus = {c.strip() for c in args.only.split(",")}
        cibles = [v for v in VERSIONS if v[0] in voulus]
        inconnus = voulus - {v[0] for v in VERSIONS}
        if inconnus:
            print("code(s) langue inconnu(s) : %s" % ", ".join(sorted(inconnus)),
                  file=sys.stderr)
            return 2
    if not cibles:
        print("rien à faire", file=sys.stderr)
        return 2

    if args.out:
        os.makedirs(args.out, exist_ok=True)

    ok = echecs = sautes = 0
    for code, nom, langue in cibles:
        etiquette = "%-4s %-22s %-18s" % (code, nom, langue)
        dest = os.path.join(args.out, nom) if args.out else None

        if dest and os.path.exists(dest) and not args.force:
            print("%s → déjà présent (%d o), ignoré"
                  % (etiquette, os.path.getsize(dest)))
            sautes += 1
            continue

        try:
            blob, url, codec = recuperer(nom, args.source)
        except Refus as e:
            print("%s → ÉCHEC : %s" % (etiquette, e))
            echecs += 1
            continue

        origine = "origine" if url.startswith(BASE) else "wayback"
        if dest:
            with open(dest, "wb") as f:
                f.write(blob)
            print("%s → %d o, codec %s, via %s" % (etiquette, len(blob), codec, origine))
        else:
            print("%s → disponible, %d o, codec %s, via %s"
                  % (etiquette, len(blob), codec, origine))
        ok += 1
        time.sleep(0.5)  # on ne martèle pas un serveur de 2004

    print("\n%d ok, %d échec(s), %d ignoré(s)" % (ok, echecs, sautes))
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
