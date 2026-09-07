#!/usr/bin/env python3
"""
Extracteur de ressources pour films Shockwave Director compressés (Afterburner).

Format vérifié empiriquement sur loading.dcr de Simon Swears. Voir CLAUDE.md
pour la description du conteneur et les pièges connus.

Usage :
    python3 dcr_extract.py film.dcr --list
    python3 dcr_extract.py film.dcr --out out/
    python3 dcr_extract.py film.dcr --out out/ --audio
"""

import argparse
import os
import struct
import sys
import zlib
from collections import Counter

# Tags susceptibles de contenir du son dans un film Director.
TAGS_AUDIO = {"snd ", "sndH", "sndS", "ediM"}

# Types de compression déclarés par le chunk Fcdr. Sur Simon Swears, Fcdr
# annonce deux codecs : 0 = « Macromedia ziplib compression », 1 = SWA, avec
# la mention « This movie requires the SWA Decompression Xtra ».
# SWA (Shockwave Audio) est du MP3 : la charge d'un `snd ` en ctype 1 est un
# en-tête sonore Macintosh suivi de trames MPEG audio, qu'on peut donc écrire
# telles quelles sans réencodage.
CTYPE_ZLIB = 0
CTYPE_SWA = 1


class Lecteur:
    """Curseur sur un tampon d'octets, gros-boutiste."""

    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos

    def fini(self):
        return self.pos >= len(self.buf)

    def u32(self):
        v = struct.unpack_from(">I", self.buf, self.pos)[0]
        self.pos += 4
        return v

    def tag(self):
        v = self.buf[self.pos:self.pos + 4]
        self.pos += 4
        return v.decode("latin1")

    def prendre(self, n):
        v = self.buf[self.pos:self.pos + n]
        self.pos += n
        return v

    def varint(self):
        """Entier gros-boutiste, 7 bits par octet, bit fort = continuation."""
        val = 0
        while True:
            octet = self.buf[self.pos]
            self.pos += 1
            val = (val << 7) | (octet & 0x7F)
            if not (octet & 0x80):
                return val


class Film:
    def __init__(self, chemin):
        self.chemin = chemin
        with open(chemin, "rb") as f:
            self.data = f.read()
        self._verifier_entete()
        self._lire_map()
        self._depaqueter()

    # --- lecture du conteneur ---------------------------------------------

    def _verifier_entete(self):
        magie = self.data[:4]
        if magie == b"XFIR":
            raise SystemExit(
                "%s : conteneur little-endian (XFIR). Ce parser ne gère que RIFX."
                % self.chemin)
        if magie != b"RIFX":
            apercu = self.data[:16].decode("latin1", "replace")
            raise SystemExit(
                "%s : ce n'est pas un film Director. Attendu 'RIFX', trouvé %r.\n"
                "Un serveur renvoyant une page d'erreur en HTTP 200 produit ce "
                "genre de fichier." % (self.chemin, apercu))

    def _lire_map(self):
        r = Lecteur(self.data)
        r.tag()
        r.u32()
        self.codec = r.tag()
        if self.codec not in ("FGDM", "FGDC"):
            raise SystemExit(
                "%s : codec %r inattendu. Un .dir ou .dxr non compressé n'est "
                "pas géré ici." % (self.chemin, self.codec))

        abmp = None
        self.version = None
        while True:
            tag = r.tag()
            longueur = r.varint()
            if tag == "FGEI":
                # Les offsets de la map partent d'ici, après le varint de longueur.
                self.base = r.pos
                break
            charge = r.prendre(longueur)
            if tag == "Fver":
                self.version = Lecteur(charge).varint()
            elif tag == "ABMP":
                interne = Lecteur(charge)
                interne.varint()   # type de compression
                interne.varint()   # taille décompressée attendue
                abmp = zlib.decompress(charge[interne.pos:])

        if abmp is None:
            raise SystemExit("%s : chunk ABMP absent." % self.chemin)

        m = Lecteur(abmp)
        m.varint()
        m.varint()
        nombre = m.varint()
        self.ressources = []
        for _ in range(nombre):
            self.ressources.append({
                "id": m.varint(),
                "offset": m.varint(),
                "csize": m.varint(),
                "dsize": m.varint(),
                "ctype": m.varint(),
                "tag": m.tag(),
            })
        self.par_id = {e["id"]: e for e in self.ressources}

    def _depaqueter(self):
        """Remplit self.blobs : id -> octets décompressés."""
        self.blobs = {}
        self.erreurs = []

        # Le segment ILS regroupe toutes les ressources dont l'offset vaut -1.
        # Attention : le fourCC est complété sur 4 octets, il ne vaut pas "ILS".
        ils = next((e for e in self.ressources
                    if e["tag"].strip("\x00 ") == "ILS"), None)
        if ils is None:
            self.erreurs.append(
                "aucun segment ILS : toutes les ressources à offset -1 seront "
                "manquantes")
        else:
            brut = self._tranche(ils)
            try:
                contenu = zlib.decompress(brut)
            except zlib.error as err:
                raise SystemExit(
                    "ILS illisible (%s). Vérifier que self.base pointe bien "
                    "après le varint de longueur de FGEI." % err)
            s = Lecteur(contenu)
            while not s.fini():
                rid = s.varint()
                entree = self.par_id.get(rid)
                if entree is None:
                    self.erreurs.append("ILS : id %d absent de la map" % rid)
                    break
                self.blobs[rid] = s.prendre(entree["dsize"])

        # Les autres sont stockées directement dans la zone FGEI.
        for e in self.ressources:
            if e["id"] in self.blobs or e["csize"] == 0:
                continue
            if e["offset"] == 0xFFFFFFFF:
                self.erreurs.append(
                    "%s#%d : offset -1 mais absent de l'ILS" % (e["tag"], e["id"]))
                continue
            if e["tag"].strip("\x00 ") == "ILS":
                continue
            brut = self._tranche(e)
            if e["ctype"] == CTYPE_ZLIB and e["csize"] != e["dsize"]:
                try:
                    brut = zlib.decompress(brut)
                except zlib.error as err:
                    # On garde les octets bruts : une charge non zlib n'est pas
                    # une charge perdue. Les `snd ` en SWA passent par ici.
                    self.erreurs.append(
                        "%s#%d : zlib refusé (%s), octets bruts conservés"
                        % (e["tag"], e["id"], err))
            self.blobs[e["id"]] = brut

    def _tranche(self, e):
        debut = self.base + e["offset"]
        return self.data[debut:debut + e["csize"]]

    # --- sorties -----------------------------------------------------------

    def resume(self):
        print("fichier   : %s (%d octets)" % (self.chemin, len(self.data)))
        print("codec     : %s   version Director : %s"
              % (self.codec, hex(self.version) if self.version else "?"))
        print("ressources: %d annoncées, %d extraites"
              % (len(self.ressources), len(self.blobs)))
        compte = Counter(e["tag"] for e in self.ressources)
        print("\ntags présents :")
        for tag, n in compte.most_common():
            marque = "  <-- AUDIO" if tag in TAGS_AUDIO else ""
            print("  %-6s %4d%s" % (repr(tag)[1:-1], n, marque))
        audio = sum(n for t, n in compte.items() if t in TAGS_AUDIO)
        print("\n%d ressource(s) audio." % audio
              + ("" if audio else " Ce film ne contient pas de son."))
        if self.erreurs:
            print("\n%d avertissement(s) :" % len(self.erreurs))
            for msg in self.erreurs[:20]:
                print("  " + msg)

    def ecrire(self, dossier, audio_seulement=False):
        os.makedirs(dossier, exist_ok=True)
        ecrits = 0
        for e in self.ressources:
            blob = self.blobs.get(e["id"])
            if blob is None:
                continue
            if audio_seulement and e["tag"] not in TAGS_AUDIO:
                continue
            nom = e["tag"].strip().replace("*", "x").replace(" ", "_") or "inconnu"
            chemin = os.path.join(dossier, "%03d_%s.bin" % (e["id"], nom))
            with open(chemin, "wb") as f:
                f.write(blob)
            ecrits += 1
        print("%d ressource(s) écrite(s) dans %s" % (ecrits, dossier))
        return ecrits


def carotter_mp3(blob):
    """Repère la première trame MP3 dans un blob ediM. Renvoie l'offset ou None."""
    for i in range(len(blob) - 1):
        if blob[i] == 0xFF and (blob[i + 1] & 0xE0) == 0xE0:
            return i
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fichier")
    ap.add_argument("--list", action="store_true", help="inventaire seulement")
    ap.add_argument("--out", metavar="DOSSIER", help="écrire les ressources")
    ap.add_argument("--audio", action="store_true",
                    help="n'écrire que les ressources sonores")
    args = ap.parse_args()

    film = Film(args.fichier)
    film.resume()

    if args.out:
        print()
        film.ecrire(args.out, audio_seulement=args.audio)
        for e in film.ressources:
            if e["tag"] == "ediM" and e["id"] in film.blobs:
                pos = carotter_mp3(film.blobs[e["id"]])
                print("  ediM#%d : synchro MP3 à l'offset %s"
                      % (e["id"], pos if pos is not None else "introuvable"))
    elif not args.list:
        print("\n(rien écrit : ajouter --out DOSSIER)")


if __name__ == "__main__":
    main()
