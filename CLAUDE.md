# Simon Swears — préservation et remake

## Objectif

Deux objectifs, dans cet ordre de priorité.

1. **Retrouver et extraire les sources originales** du jeu Shockwave « Simon Swears »
   de Joe Tree (diyjoe.com), pour les douze versions linguistiques. Le but concret
   est de récupérer les **échantillons audio exacts** : les insultes enregistrées,
   langue par langue. C'est le cœur du projet.
2. **Refaire le jeu en web moderne**, en HTML/CSS/JS sans dépendance, en utilisant
   ces sons une fois récupérés. Un prototype jouable existe déjà avec de la synthèse
   vocale en bouche-trou.

L'ordre compte : le remake n'a d'intérêt qu'avec les vrais sons. Ne pas passer du
temps à peaufiner le jeu tant que la piste d'extraction n'est pas épuisée.

## État actuel

Fait :

- Identification du format. Le jeu n'est **pas du Flash**, c'est du **Shockwave
  (Adobe Director)**. Shockwave Player a été arrêté en avril 2019.
- `assets/loading.dcr` (19 918 octets) récupéré depuis le site encore en ligne,
  et intégralement parsé. C'est **l'écran de sélection de langue**, pas le jeu.
- Parser Afterburner fonctionnel : `tools/dcr_extract.py`. Il sort les 147
  ressources exploitables de `loading.dcr`.
- Prototype web jouable : `web/simon-swears.html`.
- **Les douze `.dcr` de jeu sont acquis** (2026-09-07), depuis le serveur
  d'origine qui les sert toujours. Outil : `tools/fetch_dcr.py`. Tous validés
  `RIFX` / codec `FGDM`, entre 358 et 438 Ko. Voir Piste A pour le détail.
- Chacun des douze contient **11 ressources `snd `**. Ni `ediM` ni `sndH`/`sndS` :
  l'audio est en ancien format Macintosh `snd `, pas en Shockwave Audio.

Pas fait :

- Aucun son décodé. Les 11 `snd ` par film sont localisés mais pas convertis
  en fichiers écoutables. C'est l'étape suivante, voir Piste B.
- Le parser sort 110 ressources sur 124 annoncées pour `simonswears.dcr`, et
  signale `incorrect header check` sur chaque `snd `. Attendu : les charges
  `snd ` ne sont pas zlib. Le repli sur octets bruts doit être vérifié.

## Ce que contient loading.dcr

151 entrées dans la map : 62 `CASt`, 47 `Lscr`, 16 `BITD` (les drapeaux), 2 `CAS*`,
2 `LctX`, 2 `Cinf`, 2 `Lnam`, plus les chunks de structure (`KEY*`, `VWSC`, `VWFI`,
`Sord`, `FXmp`, `MCsL`, `XTRl`, `DRCF`, `Fmap`, `SCVW`, `XMED`, `ALFA`, `VERS`).
Zéro `snd `, `sndH`, `sndS` ou `ediM`.

Les 47 `Lscr` sont des comportements de sprite `mouseUp` qui appellent
`gotoNetMovie` sur un fichier frère. D'où la liste des cibles :

| Fichier | Langue |
|---|---|
| `simonswears.dcr` | anglais |
| `simonswears-fr.dcr` | français |
| `simonswears-cfr.dcr` | français canadien |
| `simonswears-de.dcr` | allemand |
| `simonswears-it.dcr` | italien |
| `simonswears-nl.dcr` | néerlandais |
| `simonswears-pt.dcr` | portugais |
| `simonswears-rs.dcr` | russe |
| `simonswears-jp.dcr` | japonais |
| `simonswears-tk.dcr` | turc |
| `simonswears-hb.dcr` | hébreu |
| `simonswears-n.dcr` | norvégien |

Le chunk `VWFI` contient les métadonnées de production :
`Joe Tree - Rocket Visuals Limited` et le chemin disque de l'auteur
`3MoonBase beta:Users:joetree:diyjoe.com:simonswears:`. Ce chemin suggère que les
fichiers étaient servis depuis un répertoire `simonswears/` à la racine du domaine,
mais ce n'est pas une certitude : à vérifier.

## Piste A — acquisition des .dcr — **résolue**

Les douze fichiers étaient toujours servis par le serveur d'origine, dans le
même répertoire que `loading.dcr` :

```
https://www.diyjoe.com/simonswears/simonswears.dcr        (anglais)
https://www.diyjoe.com/simonswears/simonswears-<code>.dcr (les onze autres)
```

Le chemin disque de l'auteur lu dans `VWFI` disait vrai : le répertoire est bien
`simonswears/` à la racine du domaine.

`python3 tools/fetch_dcr.py --out assets/` rejoue l'acquisition. Il valide chaque
corps avant écriture (`RIFX` ou `XFIR`, codec `FGDM`/`FGDC`/`MV93`) et refuse
explicitement le HTML servi en 200, avec la raison. Ajouter `--list` pour sonder
sans écrire, `--only fr,de` pour un sous-ensemble, `--source wayback` pour forcer
le repli.

Deux notes qui corrigent des suppositions antérieures :

- **Il n'y a plus de robots.txt sur diyjoe.com** — la requête renvoie un 404 en
  HTML. Aucun blocage d'agent automatisé constaté. Un User-Agent de navigateur
  est quand même envoyé, et une pause d'une demi-seconde sépare les requêtes.
- **La Wayback Machine ne sert que de repli, et il est mince.** Elle n'a archivé
  que `loading.dcr`, en 2004 et 2006 : les crawlers ne suivent pas les appels
  `gotoNetMovie`, qui sont du Lingo. Les douze films n'y sont pas.

Le serveur peut disparaître à tout moment. Les `.dcr` d'`assets/` sont désormais
la seule copie connue et doivent être commités.

Reste ouvert : **contacter Joe Tree / Rocket Visuals Limited** pour la question
des droits, voir plus bas.

## Piste B — extraction

### Format Afterburner, tel qu'établi sur loading.dcr

Ces détails ont été vérifiés empiriquement sur le fichier réel, pas repris d'une
spec. Ils sont fiables pour ce fichier et devraient l'être pour les autres, mais si
un `.dcr` de jeu ne parse pas, c'est ici qu'il faut regarder.

```
RIFX                      4 octets
taille                    uint32 big-endian (taille du fichier moins 8)
'FGDM'                    codec Afterburner ('FGDC' existe aussi)
puis une suite de chunks : fourCC + varint longueur + données
  'Fver'  version de Director (0x501 ici)
  'Fcdr'  table des codecs, zlib
  'ABMP'  la map des ressources, zlib
  'FGEI'  longueur varint valant 0, les données suivent immédiatement
```

Le **varint** est un entier gros-boutiste à 7 bits par octet, le bit de poids fort
servant de bit de continuation.

Point qui a coûté du temps : **les offsets de la map sont relatifs au premier octet
après le varint de longueur de `FGEI`**, pas après le fourCC. Un décalage d'un octet
fait échouer toutes les décompressions avec `incorrect header check`.

`ABMP` décompressé se lit ainsi :

```
varint unk1, varint unk2, varint nombre_de_ressources
puis par ressource :
  varint resId
  varint offset          0xFFFFFFFF = la ressource est dans l'ILS
  varint tailleCompressée
  varint tailleDécompressée
  varint typeCompression  0 = zlib
  4 octets fourCC
```

**Le segment ILS** est la ressource d'id 2, tag `ILS`, à l'offset 0. Il est
zlib-compressé et contient, concaténées, toutes les ressources dont l'offset vaut
`0xFFFFFFFF`. Après décompression, il se lit en boucle : `varint resId`, puis
exactement `tailleDécompressée` octets pris dans la map pour cet id. Dans
`loading.dcr`, 126 des 147 ressources viennent de là.

Pour les ressources stockées directement dans `FGEI` : tenter `zlib.decompress`, et
retomber sur les octets bruts en cas d'échec. En pratique, `tailleCompressée ==
tailleDécompressée` signale un stockage non compressé.

### Récupérer l'audio

C'est l'objectif. Dans un film Director, le son n'est pas un seul chunk :

- `snd ` — ressource sonore façon Macintosh, ancien format.
- `sndH` + `sndS` — le couple habituel : en-tête d'un côté (fréquence
  d'échantillonnage, profondeur, canaux, points de boucle), échantillons PCM bruts
  de l'autre. Les deux se rattachent au même membre de cast.
- `ediM` — son compressé en Shockwave Audio, c'est-à-dire du MP3. **Très probable
  ici**, puisque le jeu était destiné au web en modem.

Marche à suivre :

1. Lister les tags présents avant tout. `tools/dcr_extract.py --list` le fait.
2. Si `ediM` : les données sont des trames MP3. Chercher la synchro `FF FB` ou
   `FF F3`, découper à partir de là, écrire en `.mp3` et tester avec `ffprobe`.
   Souvent le fichier est directement lisible sans traitement.
3. Si `sndH` + `sndS` : reconstruire un en-tête WAV autour du PCM de `sndS`. Ne pas
   deviner les paramètres. Les récupérer depuis `sndH` et **les recouper avec le
   membre `CASt` associé**, qui porte aussi la fréquence, la profondeur et le nombre
   de canaux. En cas de doute, essayer 22050 puis 11025 Hz, 8 puis 16 bits, mono,
   et écouter : un mauvais réglage s'entend immédiatement.
4. Le chunk `KEY*` fait le lien entre un membre de cast et ses ressources
   associées. C'est lui qu'il faut lire pour savoir quel `sndS` va avec quel `CASt`,
   donc pour nommer les fichiers de sortie correctement plutôt que `047_sndS.bin`.
5. Les noms des membres de cast sont dans les `CASt` eux-mêmes. Dans `loading.dcr`
   ils sont explicites (`go english`, `go de`, `Loading loop`). Il y a de bonnes
   chances que les sons du jeu soient nommés lisiblement aussi, ce qui donnerait
   directement la correspondance couleur/mot.

### Références utiles

- **ProjectorRays** — décompilateur Director open source en C++. C'est
  l'implémentation de référence pour le format Afterburner et pour le bytecode
  Lingo. À consulter en cas de désaccord avec le parser.
- `shockwave.bms` d'aluigi — script QuickBMS qui décrit la décompression d'un `.dcr`.
- La page Shockwave (Director) du wiki fileformats d'ArchiveTeam.

Ne pas réimplémenter un décompilateur Lingo. Si le bytecode des `Lscr` du jeu
devient nécessaire pour comprendre la logique, passer par ProjectorRays.

## Piste C — le remake web

`web/simon-swears.html`, autonome, un seul fichier. Il fonctionne déjà :

- Quatre quadrants, disposition Simon classique, vert / rouge / jaune / bleu.
- Les quatre notes du Simon d'origine générées en Web Audio : mi 329,63 Hz,
  do# 277,18 Hz, la 220 Hz, mi grave 164,81 Hz.
- Les mots passent par `speechSynthesis`, avec un pitch distinct par couleur.
  **C'est le bouche-trou à remplacer par les vrais échantillons.**
- La séquence attend la fin réelle de chaque énoncé via `onend`, avec un garde-fou
  à 1,6 s parce que certains navigateurs ne déclenchent jamais l'événement.
- Tempo dégressif de 720 ms à 340 ms, mots éditables, presets FR et EN, clavier 1-4.

Quand les sons arriveront, remplacer la couche vocale par un lecteur d'échantillons
Web Audio : décoder une fois au démarrage dans un `AudioBuffer` par mot, jouer via
`AudioBufferSourceNode`. La durée réelle du buffer remplacera alors le garde-fou de
1,6 s, et le timing deviendra exact. Garder la synthèse vocale en repli pour les
langues dont on n'aurait pas retrouvé les fichiers.

Contraintes du prototype à conserver :

- Aucune dépendance à installer, aucun build. Un fichier qu'on ouvre.
- Pas de `localStorage` si le fichier doit tourner dans un artifact Claude.
- Accessible : focus clavier visible, `prefers-reduced-motion` respecté.

## Conventions

- Commentaires et messages de commit en français.
- Python 3 pour l'outillage, bibliothèque standard uniquement autant que possible.
  `zlib` et `struct` suffisent pour le parsing.
- Les binaires extraits vont dans `out/`, jamais commités.
- Les `.dcr` d'origine vont dans `assets/`, commités : ce sont des pièces d'archive
  et ils sont petits.
- Un échec de parsing doit dire **quelle ressource** et **pourquoi**, pas remonter
  une exception nue.

## Droits

Les enregistrements et les images appartiennent à Joe Tree / Rocket Visuals Limited.
L'extraction pour archivage et étude personnelle est une chose, la republication en
est une autre. Pour toute version publiée en ligne : soit obtenir l'accord de
l'auteur, soit réenregistrer les voix. Les sons extraits servent de référence de
timing et de ton, pas de matière première à redistribuer telle quelle.

## Arborescence

```
simon-swears/
├── CLAUDE.md
├── assets/
│   ├── loading.dcr           # l'écran de sélection de langue
│   └── simonswears*.dcr      # les douze films, un par langue
├── tools/
│   ├── fetch_dcr.py          # acquisition web + validation, fonctionne
│   └── dcr_extract.py        # parser Afterburner, fonctionne
├── out/                      # ressources extraites, non commité
└── web/
    └── simon-swears.html     # prototype jouable
```
