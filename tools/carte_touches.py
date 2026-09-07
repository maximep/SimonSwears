#!/usr/bin/env python3
"""
Retrouve quelle insulte va à quelle couleur, en lisant la partition du film.

La question ne se règle pas en décompilant le Lingo : elle se règle en suivant
les données. Le raisonnement, de bout en bout :

1. Les quatre comportements de touche sont des `Lscr` qui contiennent chacun,
   en clair dans leurs littéraux, un nom de son et une étiquette `checkN`.
   D'où l'appariement son <-> numéro de touche.
2. `VWLB` donne le numéro de trame de chaque étiquette. Attention : la table
   contient `nombre + 1` paires (trame, offset), la dernière bornant le texte.
   Se tromper là-dessus décale tous les libellés d'un cran — et l'erreur est
   discrète, parce que les trames restent plausibles.
3. `VWSC` déroulé jusqu'à la trame `checkN` montre qu'un seul canal de sprite
   reste visible : c'est la touche que le jeu met en avant.
4. Le canal porte un numéro de membre, que `CAS*` traduit en ressource `CASt`,
   qui pointe vers un `BITD`.
5. Le `BITD` décodé donne la couleur.

Usage :
    python3 carte_touches.py assets/simonswears.dcr
    python3 carte_touches.py assets/*.dcr --bref
"""

import argparse
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcr_extract as D

SONS = [b"fuck", b"bollocks", b"wanker", b"bastard"]
COULEURS = [("vert", (0, 255, 0)), ("rouge", (255, 0, 0)),
            ("jaune", (255, 255, 0)), ("bleu", (0, 0, 255))]


def chunk(film, tag):
    ids = [e["id"] for e in film.ressources if e["tag"] == tag]
    for i in ids:
        if i in film.blobs:
            return film.blobs[i]
    return None


def touches_et_etiquettes(film):
    """{numéro de check -> nom du son}, d'après les littéraux des Lscr."""
    carte = {}
    for e in film.ressources:
        if e["tag"] != "Lscr" or e["id"] not in film.blobs:
            continue
        b = film.blobs[e["id"]]
        m = re.search(rb"check([1-4])", b)
        if not m:
            continue
        for s in SONS:
            if s in b:
                carte[int(m.group(1))] = s.decode()
                break
    return carte


def etiquettes(film):
    """{nom d'étiquette -> numéro de trame}, lu dans VWLB."""
    b = chunk(film, "VWLB")
    if not b:
        return {}
    n, = struct.unpack_from(">H", b, 0)
    # n+1 paires : la dernière ne sert qu'à borner la chaîne précédente.
    paires = [struct.unpack_from(">HH", b, 2 + 4 * i) for i in range(n + 1)]
    zone = b[2 + 4 * (n + 1):]
    out = {}
    for i in range(n):
        d, fin = paires[i][1], paires[i + 1][1]
        out[zone[d:fin].decode("latin1")] = paires[i][0]
    return out


def derouler_partition(film):
    """Rejoue le flux de deltas. Renvoie (états par trame, taille d'un sprite)."""
    sc = chunk(film, "VWSC")
    n, = struct.unpack_from(">i", sc, 12)
    offs = [struct.unpack_from(">i", sc, 24 + 4 * i)[0] for i in range(n + 1)]
    base = 24 + 4 * (n + 1)
    flux = sc[base + offs[0]: base + offs[1]]

    entete, = struct.unpack_from(">I", flux, 4)
    taille_sprite, = struct.unpack_from(">H", flux, 14)
    canaux, = struct.unpack_from(">H", flux, 18)

    buf = bytearray(taille_sprite * (canaux + 2))
    pos, trame, etats = entete, 0, {}
    while pos + 2 <= len(flux):
        lg, = struct.unpack_from(">H", flux, pos)
        if lg < 2:
            break
        fin, p = pos + lg, pos + 2
        while p + 4 <= fin:
            t, o = struct.unpack_from(">HH", flux, p)
            p += 4
            d = flux[p:p + t]
            p += t
            if o + len(d) <= len(buf):
                buf[o:o + len(d)] = d
        trame += 1
        etats[trame] = bytes(buf)
        pos = fin
    return etats, taille_sprite


def index_cast(film):
    """{numéro de membre -> id de ressource CASt} pour la distribution interne."""
    meilleur = {}
    for e in film.ressources:
        if e["tag"] != "CAS*" or e["id"] not in film.blobs:
            continue
        b = film.blobs[e["id"]]
        ids = struct.unpack(">%dI" % (len(b) // 4), b[:len(b) // 4 * 4])
        table = {i: r for i, r in enumerate(ids, start=1) if r}
        if len(table) > len(meilleur):
            meilleur = table
    return meilleur


def packbits(src, attendu):
    out, i = bytearray(), 0
    while i < len(src) and len(out) < attendu:
        n = src[i]
        i += 1
        if n < 128:
            out += src[i:i + n + 1]
            i += n + 1
        else:
            if i >= len(src):
                break
            out += bytes([src[i]]) * (257 - n)
            i += 1
    return bytes(out)


def couleur_du_membre(film, cid, liens_bitd):
    """Teinte moyenne des pixels colorés du bitmap d'un membre, ou None."""
    if cid not in film.blobs or cid not in liens_bitd:
        return None
    c = film.blobs[cid]
    _t, lgi, lgd = struct.unpack_from(">III", c, 0)
    data = c[12 + lgi:12 + lgi + lgd]
    if len(data) < 10:
        return None
    pitch = struct.unpack_from(">H", data, 0)[0] & 0x7FFF
    top, left, bottom, right = struct.unpack_from(">hhhh", data, 2)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0 or pitch < 2 * w:
        return None
    brut = packbits(film.blobs[liens_bitd[cid]], pitch * h)

    sr = sg = sb = n = 0
    for y in range(0, h, 2):
        lig = brut[y * pitch:(y + 1) * pitch]
        if len(lig) < 2 * w:
            continue
        hi, lo = lig[:w], lig[w:2 * w]
        for x in range(0, w, 2):
            v = (hi[x] << 8) | lo[x]
            r, g, b = ((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3
            if max(r, g, b) - min(r, g, b) < 24:   # blanc, noir ou gris
                continue
            sr += r; sg += g; sb += b; n += 1
    return (sr // n, sg // n, sb // n) if n else None


def nommer(rgb):
    """Nom de couleur le plus proche, en teinte normalisée."""
    def norme(c):
        m = max(c) or 1
        return tuple(v / m for v in c)
    a = norme(rgb)
    return min(COULEURS, key=lambda c: sum((x - y) ** 2 for x, y in zip(a, norme(c[1]))))[0]


def analyser(chemin):
    film = D.Film(chemin)
    sons = touches_et_etiquettes(film)
    etiq = etiquettes(film)
    etats, ts = derouler_partition(film)
    membres = index_cast(film)

    liens_bitd = {}
    k = chunk(film, "KEY*")
    he, le_, _nmax, nutil = struct.unpack_from(">HHII", k, 0)
    for i in range(nutil):
        o = he + i * le_
        rid, own = struct.unpack_from(">II", k, o)
        if k[o + 8:o + 12].strip(b"\x00 ") == b"BITD":
            liens_bitd[own] = rid

    # Les canaux visibles à chaque trame checkN. Le décor est visible aux quatre,
    # donc on ne retient que ce qui distingue une trame des trois autres : le
    # canal allumé là et nulle part ailleurs, qui est la touche mise en avant.
    visibles = {}
    for num in (1, 2, 3, 4):
        cle = "check%d" % num
        if cle not in etiq or etiq[cle] not in etats:
            continue
        etat = etats[etiq[cle]]
        vus = {}
        for ch in range(1, len(etat) // ts):
            mem, = struct.unpack_from(">H", etat[ch * ts:(ch + 1) * ts], 6)
            if mem:
                vus[ch] = mem
        visibles[num] = vus

    resultat = {}
    for num, vus in visibles.items():
        ailleurs = set()
        for autre, v in visibles.items():
            if autre != num:
                ailleurs |= set(v)
        propres = [(ch, m) for ch, m in vus.items() if ch not in ailleurs]
        if len(propres) != 1:
            resultat[num] = (sons.get(num), None, None,
                             "%d canal(aux) propre(s) à cette trame, attendu 1"
                             % len(propres))
            continue
        ch, mem = propres[0]
        cid = membres.get(mem)
        rgb = couleur_du_membre(film, cid, liens_bitd) if cid else None
        if rgb is None:
            resultat[num] = (sons.get(num), None, None,
                             "canal %d, membre %d : bitmap illisible" % (ch, mem))
            continue
        resultat[num] = (sons.get(num), rgb, nommer(rgb), None)
    return resultat


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fichiers", nargs="+")
    ap.add_argument("--bref", action="store_true", help="une ligne par film")
    args = ap.parse_args()

    for chemin in args.fichiers:
        try:
            r = analyser(chemin)
        except Exception as err:
            print("%s : analyse impossible (%s)" % (os.path.basename(chemin), err),
                  file=sys.stderr)
            continue
        if args.bref:
            print("%-24s %s" % (os.path.basename(chemin),
                  "  ".join("%s=%s" % (r[n][2], r[n][0]) for n in sorted(r) if r[n][2])))
            continue
        print("%s" % os.path.basename(chemin))
        for num in sorted(r):
            son, rgb, nom, souci = r[num]
            if souci:
                print("   check%d : %s" % (num, souci))
            else:
                print("   check%-2d  %-9s  #%02x%02x%02x  %s"
                      % (num, son, rgb[0], rgb[1], rgb[2], nom))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
