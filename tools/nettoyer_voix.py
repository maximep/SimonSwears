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
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Longueur du fragment servant d'empreinte, en secondes. Assez pour caractériser
# le bruit, assez court pour ne pas mordre sur la première syllabe.
EMPREINTE = 0.18

# Seuil de détourage. -38 dB laisse passer les fins de mot qui s'éteignent, sans
# garder le souffle. Plus haut, on coupe les consonnes finales.
SEUIL_SILENCE = "-38d"


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


def nettoyer(source, dest, force, garder_wav=None):
    """Décode, débruite, détoure, normalise, encode. Renvoie une fiche."""
    tmp = tempfile.mkdtemp(prefix="voix-")
    try:
        brut = os.path.join(tmp, "brut.wav")
        profil = os.path.join(tmp, "bruit.prof")
        propre = os.path.join(tmp, "propre.wav")

        # 1. Décodage en WAV mono 48 kHz, sans retouche.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", source,
                "-ar", "48000", "-ac", "1", brut])
        avant = mesurer(brut)

        # 2. Empreinte du bruit, prise sur le tout début du fichier.
        lancer(["sox", brut, "-n", "trim", "0", str(EMPREINTE), "noiseprof", profil])

        # 3. Soustraction du bruit, coupe-bas contre les grondements de table
        #    et de manipulation, détourage des silences aux deux bouts, puis
        #    normalisation à -1 dBFS pour laisser un peu de marge à l'encodeur.
        lancer(["sox", brut, propre,
                "noisered", profil, str(force),
                "highpass", "80",
                "silence", "1", "0.05", SEUIL_SILENCE,
                "reverse",
                "silence", "1", "0.05", SEUIL_SILENCE,
                "reverse",
                "norm", "-1"])
        apres = mesurer(propre)

        # 4. Encodage MP3 mono. Les navigateurs le lisent nativement, et c'est
        #    le format des sons d'origine du jeu.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", propre,
                "-ac", "1", "-c:a", "libmp3lame", "-q:a", "4", dest])

        if garder_wav:
            shutil.copy(propre, garder_wav)
        return {"avant": avant, "apres": apres, "octets": os.path.getsize(dest)}
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

    print("réduction de bruit : %.2f\n" % args.force)
    print("%-34s %-19s %-19s %8s" % ("fichier", "avant", "après", "sortie"))
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
            f = nettoyer(source, dest, args.force, garder)
        except RuntimeError as err:
            print("%-34s ÉCHEC : %s" % (os.path.basename(source), err))
            continue
        da, pa, ra = f["avant"]
        dp, pp, rp = f["apres"]
        print("%-34s %5.2fs crête %.2f  %5.2fs crête %.2f  %6d o"
              % (os.path.basename(dest), da, pa, dp, pp, f["octets"]))
        ok += 1

    print("\n%d fichier(s) sur %d traité(s) dans %s" % (ok, len(entrees), args.out))
    if args.comparer:
        print("originaux décodés dans %s, pour comparer à l'oreille." % avant_dir)
    return 0 if ok == len(entrees) else 1


if __name__ == "__main__":
    sys.exit(main())
