#!/usr/bin/env python3
"""
Nettoyage des prises de voix pour les packs linguistiques.

Pensé pour des mémos vocaux WhatsApp, qui arrivent en Opus mono très compressé,
déjà normalisés et limités à pleine échelle par l'application. On ne peut pas
récupérer ce que l'encodage a jeté ; on peut en revanche retirer le bruit de
fond, détourer les silences et égaliser les niveaux entre les prises.

La réduction de bruit se fait **par empreinte** et non à l'aveugle : on prélève
un fragment sans voix au début du fichier, sox en tire un profil du bruit
ambiant, puis le soustrait. C'est nettement plus doux pour la voix qu'un filtre
générique, qui étouffe les consonnes en même temps que le souffle.

Dépendances externes : ffmpeg (décodage, encodage) et sox (empreinte de bruit).
    brew install ffmpeg sox

Usage :
    python3 nettoyer_voix.py assets/*.opus --out out/esar
    python3 nettoyer_voix.py assets/*.opus --out out/esar --force 0.3
    python3 nettoyer_voix.py assets/*.opus --out out/esar --comparer
"""

import argparse
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Longueur du fragment servant d'empreinte, en secondes. Assez pour caractériser
# le bruit, assez court pour ne pas mordre sur la première syllabe.
EMPREINTE = 0.18

# Marge, en décibels, entre le plancher de bruit mesuré et le seuil de coupe.
#
# Un seuil fixe ne marche pas : le plancher varie d'une prise à l'autre et,
# sur des mémos WhatsApp déjà normalisés, il remonte assez haut pour passer
# au-dessus d'un seuil choisi d'avance — le détourage ne mord alors plus rien.
# On mesure donc le plancher de chaque fichier après débruitage et on coupe
# au-dessus.
#
# 14 dB, réglé à la mesure et non au jugé. Sur ces prises, en observant
# l'énergie par tranches de 25 ms au début du fichier : à +9 dB le son démarre
# 5 dB sous le corps du mot puis y monte en 50 ms — c'est du souffle résiduel
# qu'on entend avant la voix. À +14 dB il démarre d'emblée au niveau du corps.
# Au-delà de +16 la coupe entame l'attaque : à +18, deux prises perdaient 0,3 s
# de mot. La fenêtre utile est étroite, d'où le réglage exposé en option.
MARGE_DB = 14.0

# Bornes de sécurité sur le seuil calculé, au cas où la mesure dérape — un
# fichier sans aucun silence initial donnerait un plancher aberrant.
SEUIL_MIN_DB, SEUIL_MAX_DB = -50.0, -24.0

# Durée d'audio au-dessus du seuil qui déclenche « ce n'est plus du silence ».
# Court, pour coller à l'attaque ; pas trop, pour qu'un craquement isolé ne
# déclenche pas la coupe.
DECLENCHE = "0.03"

# Fondu appliqué aux deux bouts après la coupe. Sans lui, trancher en plein
# milieu d'une onde produit un clic parfaitement audible.
FONDU = "0.008"


def besoin(outil):
    if shutil.which(outil) is None:
        sys.exit("%s est introuvable. Installer avec : brew install ffmpeg sox" % outil)


def lancer(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s a échoué :\n%s" % (cmd[0], r.stderr.strip()[-500:]))
    return r


def mesurer(wav):
    """Renvoie (durée, amplitude crête, RMS) d'après sox."""
    r = subprocess.run(["sox", wav, "-n", "stat"], capture_output=True, text=True)
    champs = {}
    for ligne in r.stderr.splitlines():
        if ":" in ligne:
            cle, _, val = ligne.partition(":")
            try:
                champs[cle.strip().lower()] = float(val.strip())
            except ValueError:
                pass
    return (champs.get("length (seconds)", 0.0),
            champs.get("maximum amplitude", 0.0),
            champs.get("rms     amplitude", 0.0))


def rms_db(wav, debut, duree):
    """Niveau RMS d'un fragment, en dBFS. -120 si c'est le silence absolu."""
    r = subprocess.run(["sox", wav, "-n", "trim", str(debut), str(duree), "stat"],
                       capture_output=True, text=True)
    for ligne in r.stderr.splitlines():
        if ligne.lower().startswith("rms     amplitude"):
            try:
                v = float(ligne.partition(":")[2])
            except ValueError:
                break
            return 20 * math.log10(v) if v > 0 else -120.0
    return -120.0


def nettoyer(source, dest, force, marge=None, garder_wav=None):
    """Décode, débruite, détoure, normalise, encode. Renvoie une fiche."""
    tmp = tempfile.mkdtemp(prefix="voix-")
    try:
        brut = os.path.join(tmp, "brut.wav")
        profil = os.path.join(tmp, "bruit.prof")
        debruite = os.path.join(tmp, "debruite.wav")
        propre = os.path.join(tmp, "propre.wav")

        # 1. Décodage en WAV mono 48 kHz, sans retouche.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", source,
                "-ar", "48000", "-ac", "1", brut])
        avant = mesurer(brut)

        # 2. Empreinte du bruit, prise sur le tout début du fichier.
        lancer(["sox", brut, "-n", "trim", "0", str(EMPREINTE), "noiseprof", profil])

        # 3. Soustraction du bruit et coupe-bas contre les grondements de table
        #    et de manipulation. Pas encore de détourage : il faut d'abord
        #    savoir à quel niveau le silence se situe une fois débruité.
        lancer(["sox", brut, debruite,
                "noisered", profil, str(force),
                "highpass", "80"])

        # 4. Seuil de coupe, calculé sur ce fichier-là. C'est le point qui
        #    décide de tout : trop bas, le souffle initial reste ; trop haut,
        #    l'attaque du mot saute.
        plancher = rms_db(debruite, 0, EMPREINTE)
        m = MARGE_DB if marge is None else marge
        seuil = min(SEUIL_MAX_DB, max(SEUIL_MIN_DB, plancher + m))

        # 5. Détourage des deux bouts. En deux passes, et non en une seule :
        #    après `silence` et `reverse`, sox ne connaît plus la longueur du
        #    flux, et `fade` refuse alors de calculer un fondu de sortie. On
        #    écrit donc le fichier coupé avant de l'estomper.
        coupe = os.path.join(tmp, "coupe.wav")
        lancer(["sox", debruite, coupe,
                "silence", "1", DECLENCHE, "%.1fd" % seuil,
                "reverse",
                "silence", "1", DECLENCHE, "%.1fd" % seuil,
                "reverse"])

        # 6. Fondus aux deux bouts contre les clics, puis normalisation à
        #    -1 dBFS. Elle vient en dernier : appliquée avant, elle fausserait
        #    le seuil qu'on vient de calculer.
        lancer(["sox", coupe, propre,
                "fade", "h", FONDU, "0", FONDU,
                "norm", "-1"])
        apres = mesurer(propre)

        # 6. Encodage MP3 mono. Les navigateurs le lisent nativement, et c'est
        #    le format des sons d'origine du jeu.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", propre,
                "-ac", "1", "-c:a", "libmp3lame", "-q:a", "4", dest])

        if garder_wav:
            shutil.copy(propre, garder_wav)
        return {"avant": avant, "apres": apres, "octets": os.path.getsize(dest),
                "plancher": plancher, "seuil": seuil,
                "coupe_tete": avant[0] - apres[0]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fichiers", nargs="+")
    ap.add_argument("--out", required=True, metavar="DOSSIER")
    ap.add_argument("--force", type=float, default=0.25, metavar="N",
                    help="intensité de la réduction de bruit, 0 à 1 "
                         "(défaut 0.25 ; au-delà de 0.4 la voix devient "
                         "métallique)")
    ap.add_argument("--marge", type=float, default=MARGE_DB, metavar="DB",
                    help="marge en dB entre le plancher de bruit mesuré et le "
                         "seuil de coupe (défaut %.0f ; monter si du souffle "
                         "reste en tête, descendre si l'attaque des mots saute)"
                         % MARGE_DB)
    ap.add_argument("--comparer", action="store_true",
                    help="garder aussi l'original décodé, pour l'écoute A/B")
    args = ap.parse_args()

    besoin("ffmpeg")
    besoin("sox")
    if not 0 <= args.force <= 1:
        sys.exit("--force attend une valeur entre 0 et 1.")

    entrees = []
    for motif in args.fichiers:
        entrees.extend(sorted(glob.glob(motif)) if any(c in motif for c in "*?[")
                       else [motif])
    entrees = [f for f in entrees if os.path.isfile(f)]
    if not entrees:
        sys.exit("aucun fichier à traiter.")

    os.makedirs(args.out, exist_ok=True)
    avant_dir = os.path.join(args.out, "_avant")
    if args.comparer:
        os.makedirs(avant_dir, exist_ok=True)

    print("réduction de bruit : %.2f · marge de coupe : %+.0f dB au-dessus du "
          "plancher\n" % (args.force, MARGE_DB))
    print("%-14s %8s %8s %9s %8s %9s %8s"
          % ("fichier", "durée av.", "ap.", "coupé", "plancher", "seuil", "sortie"))
    ok = 0
    for i, source in enumerate(entrees, start=1):
        base = re.sub(r"[^a-z0-9._-]", "-", os.path.splitext(
            os.path.basename(source))[0].lower())
        # Les mémos WhatsApp portent un horodatage : on renomme par rang, plus
        # court à manipuler. Le nom définitif viendra du slot, plus tard.
        if base.startswith("whatsapp"):
            base = "prise%02d" % i
        dest = os.path.join(args.out, base + ".mp3")
        garder = os.path.join(avant_dir, base + ".wav") if args.comparer else None
        try:
            f = nettoyer(source, dest, args.force, args.marge, garder)
        except RuntimeError as err:
            print("%-34s ÉCHEC : %s" % (os.path.basename(source), err))
            continue
        da, pa, ra = f["avant"]
        dp, pp, rp = f["apres"]
        print("%-14s %7.2fs %7.2fs %8.2fs %7.1f dB %8.1f dB %7d o"
              % (os.path.basename(dest), da, dp, f["coupe_tete"],
                 f["plancher"], f["seuil"], f["octets"]))
        ok += 1

    print("\n%d fichier(s) sur %d traité(s) dans %s" % (ok, len(entrees), args.out))
    if args.comparer:
        print("originaux décodés dans %s, pour comparer à l'oreille." % avant_dir)
    return 0 if ok == len(entrees) else 1


if __name__ == "__main__":
    sys.exit(main())
