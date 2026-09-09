#!/usr/bin/env python3
"""
Nettoyage des prises de voix pour les packs linguistiques.

Pensé pour des mémos vocaux WhatsApp, qui arrivent en Opus mono très compressé,
déjà normalisés et limités à pleine échelle par l'application. On ne récupère
pas ce que l'encodage a jeté ; on peut en revanche retirer le bruit de fond,
détourer ce qui entoure la parole et égaliser les niveaux entre les prises.

Deux traitements distincts, à ne pas confondre :

1. **Réduction de bruit**, par empreinte et non à l'aveugle. On prélève un
   fragment sans voix au début du fichier, sox en tire un profil du bruit
   ambiant, puis le soustrait. Un filtre générique étoufferait les consonnes en
   même temps que le souffle.

2. **Détourage**, par détection de la parole. C'est là que se joue la propreté
   du début de fichier, et un simple seuil de niveau n'y suffit pas — voir la
   note sur `RECUL_DB`.

Dépendances externes : ffmpeg (décodage, encodage) et sox (empreinte de bruit).
    brew install ffmpeg sox

Usage :
    python3 nettoyer_voix.py assets/*.opus --out out/esar
    python3 nettoyer_voix.py assets/*.opus --out out/esar --comparer
    python3 nettoyer_voix.py assets/*.opus --out out/esar --recul 22
"""

import argparse
import array
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

# Longueur du fragment servant d'empreinte du bruit, en secondes.
EMPREINTE = 0.18

# Écart, en dB sous le pic d'enveloppe, en dessous duquel on considère qu'il n'y
# a pas de parole.
#
# Le seuil est relatif au **pic du mot**, et non au plancher de bruit. Deux
# tentatives par le plancher ont échoué sur ces prises, pour des raisons qui
# méritent d'être notées :
#
# - Un seuil absolu ne marche pas : le plancher varie d'un fichier à l'autre.
# - Un seuil relatif au plancher ne marche pas non plus, parce que le plancher
#   lui-même n'est pas mesurable de façon fiable ici. WhatsApp insère un silence
#   numérique en tête, et son antibruit rabote la fin du fichier : les moments
#   les plus faibles ne sont donc pas le bruit de salle, et tout percentile s'y
#   fait piéger. Sur une prise, le bruit du début était à -32 dB quand la mesure
#   par percentile annonçait -46 dB.
#
# Le pic, lui, est franc et se mesure sans ambiguïté. Le corps d'un mot se situe
# autour de pic-20 dB, le bruit de début nettement en dessous. 20 dB sépare donc
# les deux. Descendre à 18 ne garde que la syllabe la plus forte ; monter à 24
# laisse repasser le bruit de tête.
RECUL_DB = 20.0

# Tranche d'analyse de l'enveloppe, en secondes.
TRANCHE = 0.010

# Durée pendant laquelle il faut rester au-dessus du seuil pour que ce soit de
# la parole et non un claquement. En nombre de tranches.
TENUE = 5

# Marge conservée avant l'attaque et après la chute, en tranches. Couper au ras
# du seuil ampute les consonnes d'attaque et les fins de mot qui s'éteignent.
PREROLL, QUEUE = 4, 6

# Fondu appliqué aux deux bouts après la coupe. Sans lui, trancher en plein
# milieu d'une onde produit un clic parfaitement audible.
FONDU = "0.008"


def besoin(outil):
    if shutil.which(outil) is None:
        sys.exit("%s est introuvable. Installer avec : brew install ffmpeg sox" % outil)


def lancer(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s a échoué :\n%s" % (cmd[0], r.stderr.strip()[-400:]))
    return r


def mesurer(wav):
    """Renvoie (durée, amplitude crête) d'après sox."""
    r = subprocess.run(["sox", wav, "-n", "stat"], capture_output=True, text=True)
    champs = {}
    for ligne in r.stderr.splitlines():
        cle, _, val = ligne.partition(":")
        try:
            champs[cle.strip().lower()] = float(val.strip())
        except ValueError:
            pass
    return champs.get("length (seconds)", 0.0), champs.get("maximum amplitude", 0.0)


def enveloppe(wav):
    """Niveau RMS en dBFS par tranche de TRANCHE secondes."""
    with wave.open(wav) as w:
        if w.getsampwidth() != 2:
            raise RuntimeError("attendu du PCM 16 bits, reçu %d bits"
                               % (w.getsampwidth() * 8))
        hz = w.getframerate()
        ech = array.array("h")
        ech.frombytes(w.readframes(w.getnframes()))
    pas = int(hz * TRANCHE)
    niveaux = []
    for i in range(0, len(ech), pas):
        bloc = ech[i:i + pas]
        if len(bloc) < pas // 2:
            break
        r = math.sqrt(sum(float(v) * v for v in bloc) / len(bloc))
        niveaux.append(20 * math.log10(r / 32768.0) if r > 0 else -120.0)
    return niveaux


def bornes_parole(niveaux, recul):
    """
    (début, fin) de la parole en secondes.

    Balayage avant pour le début, arrière pour la fin : on cherche la première
    et la dernière zone qui tient au-dessus du seuil, pas la plus forte. Partir
    du pic et remonter donnerait la syllabe la plus sonore et rien d'autre.
    """
    if not niveaux:
        return None
    seuil = max(niveaux) - recul
    debut = fin = None
    for i in range(len(niveaux) - TENUE + 1):
        if all(niveaux[i + k] >= seuil for k in range(TENUE)):
            debut = max(0, i - PREROLL)
            break
    for i in range(len(niveaux) - TENUE, -1, -1):
        if all(niveaux[i + k] >= seuil for k in range(TENUE)):
            fin = min(len(niveaux), i + TENUE + QUEUE)
            break
    if debut is None or fin is None or fin <= debut:
        return None
    return debut * TRANCHE, fin * TRANCHE


def nettoyer(source, dest, force, recul, garder_wav=None):
    """Décode, débruite, détoure, normalise, encode. Renvoie une fiche."""
    tmp = tempfile.mkdtemp(prefix="voix-")
    try:
        brut = os.path.join(tmp, "brut.wav")
        profil = os.path.join(tmp, "bruit.prof")
        debruite = os.path.join(tmp, "debruite.wav")
        coupe = os.path.join(tmp, "coupe.wav")
        propre = os.path.join(tmp, "propre.wav")

        # 1. Décodage en WAV mono 48 kHz, 16 bits, sans retouche.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", source,
                "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", brut])
        duree_avant, _ = mesurer(brut)
        if garder_wav:
            shutil.copy(brut, garder_wav)   # l'original décodé, pour comparer

        # 2. Empreinte du bruit, puis soustraction et coupe-bas contre les
        #    grondements de table et de manipulation.
        lancer(["sox", brut, "-n", "trim", "0", str(EMPREINTE), "noiseprof", profil])
        lancer(["sox", brut, debruite,
                "noisered", profil, str(force), "highpass", "80"])

        # 3. Détection de la parole sur le signal débruité, puis découpe.
        bornes = bornes_parole(enveloppe(debruite), recul)
        if bornes is None:
            raise RuntimeError("aucune parole détectée (fichier vide ou trop bruité ?)")
        d, f = bornes
        lancer(["sox", debruite, coupe, "trim", "%.3f" % d, "%.3f" % (f - d)])

        # 4. Fondus contre les clics, puis normalisation à -1 dBFS. Elle vient
        #    en dernier, sinon elle fausserait les niveaux qu'on vient d'analyser.
        lancer(["sox", coupe, propre, "fade", "h", FONDU, "0", FONDU, "norm", "-1"])
        duree_apres, crete = mesurer(propre)

        # 5. Encodage MP3 mono, le format des sons d'origine du jeu.
        lancer(["ffmpeg", "-v", "error", "-y", "-i", propre,
                "-ac", "1", "-c:a", "libmp3lame", "-q:a", "4", dest])

        return {"avant": duree_avant, "apres": duree_apres, "crete": crete,
                "debut": d, "fin": f, "octets": os.path.getsize(dest)}
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
                         "(défaut 0.25 ; au-delà de 0.4 la voix devient métallique)")
    ap.add_argument("--recul", type=float, default=RECUL_DB, metavar="DB",
                    help="seuil de parole, en dB sous le pic (défaut %.0f ; "
                         "monter si du bruit reste en tête, descendre si "
                         "l'attaque des mots saute)" % RECUL_DB)
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
    dossier_avant = os.path.join(args.out, "_original")
    if args.comparer:
        os.makedirs(dossier_avant, exist_ok=True)

    print("bruit : %.2f · parole : au-dessus de pic-%.0f dB\n"
          % (args.force, args.recul))
    print("%-14s %9s %9s %16s %8s"
          % ("fichier", "durée av.", "ap.", "parole détectée", "sortie"))
    ok = 0
    for i, source in enumerate(entrees, start=1):
        base = re.sub(r"[^a-z0-9._-]", "-",
                      os.path.splitext(os.path.basename(source))[0].lower())
        # Les mémos WhatsApp portent un horodatage : on renomme par rang, plus
        # court à manipuler. Le nom définitif viendra du slot, plus tard.
        if base.startswith("whatsapp"):
            base = "prise%02d" % i
        dest = os.path.join(args.out, base + ".mp3")
        garder = os.path.join(dossier_avant, base + ".wav") if args.comparer else None
        try:
            f = nettoyer(source, dest, args.force, args.recul, garder)
        except RuntimeError as err:
            print("%-14s ÉCHEC : %s" % (base, err))
            continue
        print("%-14s %8.2fs %8.2fs %7.2f→%-7.2fs %7d o"
              % (os.path.basename(dest), f["avant"], f["apres"],
                 f["debut"], f["fin"], f["octets"]))
        ok += 1

    print("\n%d fichier(s) sur %d traité(s) dans %s" % (ok, len(entrees), args.out))
    if args.comparer:
        print("originaux décodés dans %s, pour comparer à l'oreille." % dossier_avant)
    return 0 if ok == len(entrees) else 1


if __name__ == "__main__":
    sys.exit(main())
