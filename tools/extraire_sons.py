#!/usr/bin/env python3
"""
Extraction des sons de Simon Swears vers des .mp3 nommés.

Les `snd ` du jeu sont en ctype 1, c'est-à-dire SWA (Shockwave Audio), ce qui
est du MPEG audio. La charge est un en-tête sonore Macintosh suivi des trames.
On repère le début du flux, on le recopie tel quel : aucun réencodage, donc
aucune perte, et le MP3 est lisible nativement par les navigateurs.

Les noms viennent des membres de cast : le chunk KEY* dit quel `snd ` appartient
à quel CASt, et le CASt porte le nom donné par l'auteur ('fuck', 'music',
'boing2'...). D'où des fichiers nommés plutôt que des 047_snd.bin.

Usage :
    python3 extraire_sons.py assets/simonswears.dcr --out out/en
    python3 extraire_sons.py assets/*.dcr --out out/ --par-langue
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcr_extract as D

# --- en-têtes MPEG audio ---------------------------------------------------

# Débits en kbit/s, indexés par bitrate_index. MPEG1 et MPEG2/2.5 diffèrent.
DEBITS_MPEG1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
DEBITS_MPEG2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
FREQS = {3: [44100, 48000, 32000],   # MPEG1
         2: [22050, 24000, 16000],   # MPEG2
         0: [11025, 12000, 8000]}    # MPEG2.5
CANAUX = {0: "stéréo", 1: "joint-stéréo", 2: "double mono", 3: "mono"}


class Trame:
    """En-tête de trame MPEG audio décodé. `None` si l'octet n'en est pas un."""

    __slots__ = ("version", "couche", "debit", "freq", "canaux", "taille")

    def __init__(self, version, couche, debit, freq, canaux, taille):
        self.version, self.couche = version, couche
        self.debit, self.freq, self.canaux, self.taille = debit, freq, canaux, taille


def lire_trame(buf, i):
    """Décode l'en-tête de 4 octets en i. Renvoie une Trame ou None."""
    if i + 4 > len(buf):
        return None
    o1, o2, o3, o4 = buf[i], buf[i + 1], buf[i + 2], buf[i + 3]
    if o1 != 0xFF or (o2 & 0xE0) != 0xE0:
        return None
    version = (o2 >> 3) & 3          # 3=MPEG1, 2=MPEG2, 0=MPEG2.5, 1=réservé
    couche = (o2 >> 1) & 3           # 1 = Layer III
    if version == 1 or couche != 1:
        return None
    idx_debit = (o3 >> 4) & 0xF
    idx_freq = (o3 >> 2) & 3
    if idx_debit in (0, 15) or idx_freq == 3:
        return None
    bourrage = (o3 >> 1) & 1
    canaux = (o4 >> 6) & 3
    table = DEBITS_MPEG1_L3 if version == 3 else DEBITS_MPEG2_L3
    debit = table[idx_debit] * 1000
    freq = FREQS[version][idx_freq]
    # Layer III : 1152 échantillons par trame en MPEG1, 576 en MPEG2/2.5.
    coef = 144 if version == 3 else 72
    taille = (coef * debit) // freq + bourrage
    if taille < 8:
        return None
    return Trame(version, couche, debit, freq, canaux, taille)


def trouver_flux(buf, minimum=4):
    """
    Offset du premier flux MPEG valide, ou None.

    Une synchro isolée ne suffit pas : les octets 0xFF sont fréquents dans du
    PCM et dans un en-tête Macintosh. On n'accepte un offset que si au moins
    `minimum` trames s'enchaînent, chacune atterrissant exactement sur la
    suivante.
    """
    for i in range(len(buf) - 4):
        if buf[i] != 0xFF or (buf[i + 1] & 0xE0) != 0xE0:
            continue
        pos, n, premiere = i, 0, None
        while n < minimum:
            t = lire_trame(buf, pos)
            if t is None:
                break
            if premiere is None:
                premiere = t
            elif t.freq != premiere.freq or t.canaux != premiere.canaux:
                break  # un vrai flux ne change pas de fréquence en route
            pos += t.taille
            n += 1
            if pos >= len(buf):
                n = minimum  # fin de tampon atteinte proprement
                break
        if n >= minimum:
            return i, premiere
    return None, None


def compter_trames(buf):
    """Parcourt le flux et renvoie (nombre de trames, durée en secondes)."""
    pos, n, ech = 0, 0, 0
    while pos < len(buf):
        t = lire_trame(buf, pos)
        if t is None:
            break
        ech += 1152 if t.version == 3 else 576
        pos += t.taille
        n += 1
    freq = lire_trame(buf, 0).freq
    return n, ech / float(freq)


# --- noms des membres de cast ----------------------------------------------

def lire_keys(film):
    """snd id -> CASt id, d'après le chunk KEY*."""
    cles = [e["id"] for e in film.ressources if e["tag"] == "KEY*"]
    if not cles or cles[0] not in film.blobs:
        return {}
    k = film.blobs[cles[0]]
    lg_entete, lg_entree, _nmax, nutil = struct.unpack_from(">HHII", k, 0)
    liens = {}
    for i in range(nutil):
        o = lg_entete + i * lg_entree
        if o + 12 > len(k):
            break
        rid, prop = struct.unpack_from(">II", k, o)
        if k[o + 8:o + 12].strip(b"\x00 ") == b"snd":
            liens[rid] = prop
    return liens


def nom_cast(blob):
    """
    Nom du membre, lu dans la table d'items du bloc info du CASt.

    Disposition : uint32 type, uint32 longueur info, uint32 longueur data, puis
    le bloc info. Celui-ci commence par un offset vers sa table d'items ; la
    table donne n+1 bornes, et l'item 1 est le nom, en chaîne Pascal.
    """
    if len(blob) < 12:
        return None
    _type, lg_info, _lg_data = struct.unpack_from(">III", blob, 0)
    info = blob[12:12 + lg_info]
    if len(info) < 22:
        return None
    try:
        depart, = struct.unpack_from(">I", info, 0)
        n, = struct.unpack_from(">H", info, depart)
        if n < 2:
            return None
        bornes = [struct.unpack_from(">I", info, depart + 2 + 4 * j)[0]
                  for j in range(n + 1)]
        base = depart + 2 + 4 * (n + 1)
        d, fin = base + bornes[1], base + bornes[2]
    except (struct.error, IndexError):
        return None
    if not (0 <= d <= fin <= len(info)) or d == fin:
        return None
    champ = info[d:fin]
    return champ[1:1 + champ[0]].decode("latin1")


def assainir(nom):
    """Nom de fichier sûr, sans perdre la lisibilité."""
    nom = nom.strip().lower().replace(" ", "-")
    nom = re.sub(r"[^a-z0-9._-]", "", nom)
    return nom or "sans-nom"


# --- extraction -------------------------------------------------------------

def extraire(chemin, dossier, verbeux=True):
    """Écrit les sons d'un film. Renvoie la liste des fiches écrites."""
    film = D.Film(chemin)
    liens = lire_keys(film)
    noms = {}
    for e in film.ressources:
        if e["tag"] == "CASt" and e["id"] in film.blobs:
            n = nom_cast(film.blobs[e["id"]])
            if n:
                noms[e["id"]] = n

    os.makedirs(dossier, exist_ok=True)
    fiches, vus = [], {}
    for e in film.ressources:
        if e["tag"].strip("\x00 ") != "snd":
            continue
        blob = film.blobs.get(e["id"])
        if not blob:
            if verbeux:
                print("  snd#%-4d : vide (csize=%d), ignoré" % (e["id"], e["csize"]))
            continue

        debut, tete = trouver_flux(blob)
        if debut is None:
            print("  snd#%-4d : ÉCHEC, aucun flux MPEG (ctype=%d, %d octets). "
                  "Son non compressé ? À traiter en PCM."
                  % (e["id"], e["ctype"], len(blob)), file=sys.stderr)
            continue

        flux = blob[debut:]
        ntrames, duree = compter_trames(flux)
        brut = noms.get(liens.get(e["id"]), "snd%d" % e["id"])
        base = assainir(brut)
        vus[base] = vus.get(base, 0) + 1
        if vus[base] > 1:
            base = "%s-%d" % (base, vus[base])
        dest = os.path.join(dossier, base + ".mp3")
        with open(dest, "wb") as f:
            f.write(flux)

        fiche = {"id": e["id"], "nom": brut, "fichier": os.path.basename(dest),
                 "octets": len(flux), "trames": ntrames, "duree": duree,
                 "freq": tete.freq, "debit": tete.debit, "canaux": tete.canaux,
                 "entete": debut}
        fiches.append(fiche)
        if verbeux:
            print("  %-16s %-7d o  %5.2f s  %d Hz  %d kbit/s  %s  (%d trames)"
                  % (fiche["fichier"], fiche["octets"], duree, tete.freq,
                     tete.debit // 1000, CANAUX[tete.canaux], ntrames))
    return fiches


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fichiers", nargs="+")
    ap.add_argument("--out", required=True, metavar="DOSSIER")
    ap.add_argument("--par-langue", action="store_true",
                    help="un sous-dossier par film, nommé d'après le code langue")
    args = ap.parse_args()

    total = 0
    for chemin in args.fichiers:
        base = os.path.basename(chemin)
        if args.par_langue:
            m = re.match(r"simonswears(?:-(\w+))?\.dcr$", base)
            code = (m.group(1) or "en") if m else os.path.splitext(base)[0]
            dossier = os.path.join(args.out, code)
        else:
            dossier = args.out
        print("%s → %s" % (base, dossier))
        total += len(extraire(chemin, dossier))
        print()
    print("%d son(s) écrit(s)." % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
