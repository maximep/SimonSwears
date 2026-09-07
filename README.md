# Simon Swears — préservation et remake

**Simon Swears** est un jeu de **Joe Tree**, publié sur [diyjoe.com](https://www.diyjoe.com/)
vers 2004 sous *Rocket Visuals Limited* : un Simon qui jure, en douze langues,
chacune enregistrée séparément. Le tout dans un fichier Shockwave de 350 Ko, à
l'époque du modem.

Shockwave a été arrêté en avril 2019 et le jeu est devenu injouable. Ce dépôt
contient de quoi le retrouver : les outils qui extraient les sons d'origine de
ses fichiers Director, et un remake web qui les rejoue.

## Ce qu'il y a ici

| | |
|---|---|
| `tools/fetch_dcr.py` | Récupère les douze `.dcr` depuis le serveur d'origine, repli Wayback |
| `tools/dcr_extract.py` | Parser du conteneur Shockwave compressé (Afterburner) |
| `tools/extraire_sons.py` | Sort les `snd ` en MP3 nommés, sans réencodage |
| `tools/carte_touches.py` | Restitue quelle insulte va à quelle couleur, depuis la partition |
| `tools/embarquer_sons.py` | Fabrique les paquets de sons du jeu web |
| `web/simon-swears.html` | Le remake, un seul fichier, sans dépendance ni build |

`CLAUDE.md` documente le format, la méthode et les pièges rencontrés.

## Démarrer

```sh
python3 tools/fetch_dcr.py --out assets/     # les douze films d'origine
python3 tools/embarquer_sons.py --tout       # extrait les sons et les embarque
open web/simon-swears.html                   # et c'est tout
```

Python 3, bibliothèque standard uniquement. Aucun paquet à installer, aucun
serveur à lancer : le jeu est un fichier HTML qu'on ouvre.

## Quelques trouvailles

- Les sons sont du **Shockwave Audio**, c'est-à-dire du MP3, mais ils n'arrivent
  pas par le tag `ediM` attendu : ce sont des `snd ` en `ctype 1`, un en-tête
  sonore Macintosh de 82 octets suivi de trames MPEG-2 Layer III. On les recopie
  tels quels — les fichiers sont exactement ceux de 2004.
- La correspondance couleur → insulte ne demande pas de décompiler du Lingo. Les
  scripts portent leurs étiquettes en clair, la partition dit quelle touche
  s'allume à quelle trame, et le bitmap du quadrant donne la couleur.
- La Wayback Machine n'a jamais archivé les douze films : les crawlers ne suivent
  pas les appels `gotoNetMovie`. Seul le serveur d'origine les avait encore.

## Droits

Les enregistrements et les images sont l'œuvre de **Joe Tree / Rocket Visuals
Limited**. Les voix et la musique sont incluses ici (`web/sons/`) pour que le
jeu soit jouable : Shockwave est mort en 2019, et ces enregistrements n'existent
plus nulle part ailleurs sous une forme qui tourne. C'est un dépôt de
préservation, pas une appropriation — l'auteur est crédité dans le jeu lui-même.

Les `.dcr` d'origine, eux, ne sont pas dans le dépôt : `fetch_dcr.py` va les
chercher chez l'auteur, dont le serveur répond toujours.

Remake non officiel. **Si Joe Tree ou Rocket Visuals souhaite qu'on retire ces
sons, il suffit de le demander : ce sera fait sans discuter.**
