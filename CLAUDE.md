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
- **Les 130 sons sont extraits**, en MP3, sans réencodage. `tools/extraire_sons.py`.
- **Le remake utilise les vrais sons**, musique de fond comprise, avec sélecteur
  des douze langues. `tools/embarquer_sons.py` fabrique les paquets.

Pas fait :

- Rien de bloquant. La correspondance couleur → insulte, longtemps la dernière
  inconnue, est **restituée** : voir « Retrouver la carte des touches ».
- Deux films, `jp` et `rs`, n'ont pas de `boing2` : le `snd ` correspondant ne
  fait que 82 octets, l'en-tête sans charge. Slot vide chez l'auteur, pas un
  échec d'extraction.

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

Le serveur peut disparaître à tout moment, et `assets/` est la seule copie
connue — **il faut en garder une sauvegarde hors du dépôt**. Ces fichiers ne
sont pas commités : voir Conventions.

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

### Récupérer l'audio — **résolu**

Le pari du départ était bon : c'est bien du Shockwave Audio, donc du MP3. Mais
il n'arrive pas par le tag `ediM` comme supposé. Ce qu'on trouve réellement :

- **Tag `snd `, mais `ctype = 1`.** Le champ `typeCompression` de la map, que le
  parser ignorait, ne vaut pas 0. Le chunk **`Fcdr`** déclare les codecs et dit
  en clair ce que vaut l'index 1 : *« This movie requires the SWA Decompression
  Xtra »*. L'index 0 est *« Macromedia ziplib compression »*.
- **La charge n'est donc pas zlib.** Elle commence par un en-tête sonore
  Macintosh de **82 octets** — `00 02` (format 2), `0000` (refCount),
  `0001` (une commande), `8051` (`bufferCmd`) — puis les trames MPEG démarrent
  à l'offset 82, sans exception sur les 130 sons extraits.
- **MPEG-2 Layer III, mono**, 22 050 Hz pour les voix et 44 100 Hz pour les
  sons longs. Débit 48 kbit/s sur la version anglaise, 64 sur les autres.

D'où une extraction **sans réencodage** : on recopie les octets à partir de la
première trame. Les fichiers sont donc exactement ceux de 2004, et le MP3 est
lu nativement par les navigateurs — aucune conversion n'est utile.

`tools/extraire_sons.py assets/*.dcr --out out --par-langue` produit
`out/<code>/<nom>.mp3`. Deux points sur lesquels l'outil ne fait pas confiance
au hasard :

- **La synchro MP3 est validée par chaînage.** Un octet `FF` isolé est fréquent
  dans un en-tête ou du PCM ; chercher `FF Fx` et découper là donne des faux
  positifs. On n'accepte un offset que si au moins quatre trames s'enchaînent,
  chacune atterrissant exactement sur la suivante d'après la taille calculée, et
  sans changement de fréquence en route.
- **Les fichiers sont nommés, pas numérotés.** Le chunk `KEY*` relie chaque
  `snd ` à son membre `CASt`, et le `CASt` porte le nom de l'auteur. Le nom est
  l'item 1 de la table d'items du bloc info, en chaîne Pascal.

Les onze emplacements, identiques dans les douze films — Joe Tree a gardé les
identifiants anglais et n'a remplacé que l'audio :

| Emplacement | Rôle |
|---|---|
| `fuck`, `bollocks`, `wanker`, `bastard` | les quatre mots des quatre touches |
| `music` | la boucle de fond, 2,27 s |
| `boing2` | transition entre les tours |
| `welldone`, `congrats` | encouragements |
| `out`, `fuckedit` | défaite |
| `wind-down` | descente de fin de partie |

### Retrouver la carte des touches

**Quelle insulte va à quelle couleur.** Réglé, et sans décompiler une seule
instruction Lingo : la réponse était dans les données, pas dans le code.
`tools/carte_touches.py` refait le raisonnement et le vérifie.

1. Les quatre comportements de touche sont des `Lscr` qui portent, **en clair
   dans leurs littéraux**, un nom de son et une étiquette `checkN`. Il suffit de
   lire les chaînes du blob, aucun désassemblage n'est nécessaire. D'où
   l'appariement son ↔ numéro de touche.
2. `VWLB` donne le numéro de trame de chaque étiquette.
3. `VWSC` déroulé jusqu'à la trame `checkN` montre quel sprite le jeu met en
   avant : à cette trame, un canal est visible et lui seul.
4. Le canal porte un numéro de membre, que `CAS*` traduit en ressource `CASt`,
   laquelle pointe vers un `BITD`.
5. Le `BITD` décodé donne la couleur du quadrant.

Résultat, **identique dans les douze films** :

| Couleur | Emplacement | Étiquette |
|---|---|---|
| vert | `bollocks` | `check2` |
| rouge | `fuck` | `check1` |
| jaune | `wanker` | `check3` |
| bleu | `bastard` | `check4` |

C'est ce qu'applique `SLOTS_MOTS` dans le jeu. Ce n'est plus un choix par défaut.

#### Trois pièges rencontrés

- **`VWLB` contient `nombre + 1` paires** (trame, offset), la dernière servant
  seulement à borner la chaîne précédente. En lire `nombre` décale tous les
  libellés d'un cran. L'erreur est discrète : les numéros de trame restent
  plausibles, et on conclut tranquillement à l'envers. C'est ce qui a fait
  croire un moment que `check4` n'allumait aucune touche.
- **Le décor est visible aux quatre trames `checkN`.** Chercher « le canal
  allumé » en ramène une dizaine. Le bon critère est différentiel : le canal
  allumé à cette trame **et à aucune des trois autres**.
- **Le flux de trames de `VWSC` a un en-tête de 20 octets** avant les deltas, et
  c'est lui qui donne la taille d'un enregistrement de sprite (48 octets ici) et
  le nombre de canaux. Attaquer les deltas à l'offset 0 ne produit rien.

#### Structure d'un enregistrement de sprite

Établi empiriquement sur ce film, en cherchant des ancres connues — numéros de
membre et positions plausibles sur un plateau de 500×500 :

```
0     u8   type            4-5   u16  distribution
1     u8   encre           6-7   u16  numéro de membre
2     u8   couleur avant   10-11 u16  renvoi vers une entrée d'intervalle
3     u8   couleur arrière 12-13 i16  position verticale
                           14-15 i16  position horizontale
                           16-17 i16  hauteur
                           18-19 i16  largeur
```

Les quatre touches sont toutes ancrées au centre du plateau (250, 250) : c'est
le point d'accroche de chaque bitmap qui les envoie dans leur coin.

#### Les bitmaps

16 bits par pixel, RGB555, compressés en PackBits. Chaque ligne fait `pitch`
octets et se lit **en deux plans** : les octets de poids fort de la ligne
entière, puis les octets de poids faible. Les décoder en supposant des pixels
entrelacés donne une bouillie plausible mais fausse. Le contrôle qui rassure :
la sortie PackBits doit faire exactement `pitch × hauteur` octets, ce qui est le
cas sur les quatre quadrants.

### Références utiles

- **ProjectorRays** — décompilateur Director open source en C++. C'est
  l'implémentation de référence pour le format Afterburner et pour le bytecode
  Lingo. À consulter en cas de désaccord avec le parser.
- `shockwave.bms` d'aluigi — script QuickBMS qui décrit la décompression d'un `.dcr`.
- La page Shockwave (Director) du wiki fileformats d'ArchiveTeam.

Le bytecode Lingo n'a pas eu à être désassemblé : les littéraux des `Lscr` se
lisent tels quels, et la partition portait le reste. Si une question exige un
jour la logique elle-même, ProjectorRays reste la voie courte — mais commencer
par regarder les données, elles en disent plus qu'on ne croit.

## Piste C — le remake web

`web/simon-swears.html`, toujours un seul fichier sans build ni dépendance.
Les vrais échantillons ont remplacé la synthèse vocale.

- **Les douze langues** sont dans un sélecteur, chargées à la demande.
- **La musique de fond d'origine** tourne en boucle (`loop = true` sur le
  `AudioBufferSourceNode`) et **s'atténue le temps de chaque insulte**, sans
  quoi on ne comprend pas les mots. Rampe à 0,10 puis retour à 0,34.
- **Le timing est devenu exact.** La durée réelle de l'`AudioBuffer` remplace le
  garde-fou de 1,6 s qu'imposait `speechSynthesis`.
- **La synthèse vocale reste en repli**, si un paquet de sons manque. Le panneau
  d'édition des mots ne sert plus qu'à ça, et le dit.
- **Deux modes.** *Défi du jour* (par défaut) et *Partie libre*, l'ancien mode
  sans fin.
- **Partage façon Wordle**, réservé au défi du jour : un score libre ne se
  compare à rien, donc ne se partage pas. Le bouton apparaît en fin de défi et
  copie le numéro, le score sur 20, une grille de progression, le record, la
  langue et le lien. Trois points à ne pas défaire :
  - **Le partage du défi ne montre jamais la séquence.** C'est le piège du
    projet, et il a été introduit puis corrigé : au contraire de Wordle, dont
    la grille montre le *retour* sur les essais, la séquence de Simon **est**
    la réponse. Peinte en couleurs de touches, elle offrait le défi du jour à
    qui n'avait pas encore joué — un partage à 20/20 livrait la solution
    entière. `grilleProgression()` ne dit que jusqu'où le joueur est allé :
    vert par tour passé, un rouge à l'endroit de la chute, noir au-delà.
    Toute représentation des touches fuite, **même déguisée** : un simple
    décompte par couleur réduirait déjà énormément les possibilités.
  - La partie libre, elle, peut montrer sa suite : elle n'appartient qu'à cette
    partie et ne prive personne. C'est la seule raison pour laquelle
    `grille()` existe encore à côté de `grilleProgression()`.
  - `navigator.clipboard` **existe en `file://` mais rejette**, faute de
    contexte sécurisé. Tester sa présence ne suffit donc pas : il faut aussi
    rattraper son échec, sinon le repli `execCommand` ne sert jamais là où il
    est justement nécessaire.
- **Historique des parties**, alimenté par `conclure()`, le point de passage
  unique en fin de partie. Conservé en `localStorage`, douze entrées au plus.
  Il garde les **vraies couleurs**, y compris pour le défi : il ne quitte pas
  l'écran du joueur, qui connaît déjà la suite qu'il vient de jouer. Choix
  assumé — une capture d'écran de la page reste donc un moyen de divulguer le
  défi du jour, là où le texte copié, lui, n'en dit rien.
- **Bouton de soutien** vers Ko-fi, sous les réglages. Au **bleu** de la marque
  et non à son corail : essayé en corail, il ressortait plus vif que le bouton
  *Commencer* placé juste au-dessus, et les deux pastilles rouges se lisaient
  comme des jumelles — l'action principale du jeu se faisait voler la vedette
  par un lien de don. Le bleu s'oppose au brun du fond et ne ressemble à rien
  d'autre sur la page. Texte sombre et non blanc : sur un cyan aussi clair, le
  blanc tombe sous le seuil de contraste lisible.
  Il ne s'affiche **que si `LIEN_CAFE` porte une vraie adresse** ; si la
  constante repasse à `A-REMPLACER`, le bouton se masque. Un lien de don qui
  tombe à côté ne coûte pas qu'un 404 : sur une adresse habitée par quelqu'un
  d'autre, ce sont les dons qui partent chez lui.

### Le défi du jour

Vingt insultes, la même suite pour tout le monde à une date donnée, **sans
serveur** : la suite se déduit de la date, donc deux joueurs du même jour
tombent forcément dessus.

- `numeroDuJour()` compte les jours depuis le 1er janvier 2026. La date est
  prise **en heure locale**, comme Wordle : le défi change à minuit chez le
  joueur, pas à une heure imposée par un fuseau lointain.
- `generateur()` est un mulberry32. `Math.random` ne convient pas : sans graine,
  il donnerait une suite différente à chacun, ce qui vide le partage de son sens.
- Le numéro est dispersé (`Math.imul(numero, 2654435761)`) avant d'être semé.
  Sans ça, des jours consécutifs donnent des graines voisines et les premiers
  tirages se ressemblent. Vérifié sur 2000 jours : répartition des quatre
  couleurs à moins de 3 % d'écart.
- **Une tentative par jour**, comme Wordle : sinon le score partagé ne veut plus
  rien dire. La partie libre reste sans limite.

Pour changer la longueur, `LONGUEUR_DEFI` suffit — mais elle change toutes les
suites déjà jouées, donc à ne toucher qu'en connaissance de cause.

### La persistance

Tout tient dans une clé, `simon-swears:v1` : record, historique, et le verrou du
défi. Trois points qui ne sont pas décoratifs.

- **Le verrou est daté.** On stocke `{ numero }` et non un simple booléen : sans
  le numéro, avoir joué une fois bloquerait aussi tous les jours suivants. Au
  chargement, le verrou ne s'applique que si le numéro stocké est celui du jour.
- **`localStorage` peut lever à la simple lecture**, pas seulement manquer :
  navigation privée, cookies bloqués, iframe sans autorisation. D'où le
  `try`/`catch` systématique, et une **sonde d'écriture** plutôt qu'un test
  d'existence — Safari en navigation privée expose bien l'objet mais refuse d'y
  écrire. Un échec n'est jamais fatal : le jeu retombe sur la mémoire de
  l'onglet et le dit sous l'historique.
- **Ce qui est relu est filtré.** Ces données ont pu être écrites par une
  version antérieure ou trafiquées dans la console ; les entrées qui n'ont pas
  la forme attendue sont écartées.

Vérifié : rechargement après une partie (verrou tenu, historique et partage
retrouvés), lendemain simulé en vieillissant le numéro stocké (verrou levé,
historique gardé), et `localStorage` qui lève à tout coup (page jouable, note
adaptée, aucune erreur).

### Le chargement des sons, et pourquoi c'est fait comme ça

`tools/embarquer_sons.py` fabrique `web/sons/<code>.js`, un par langue, qui pose
les MP3 en `data:` URI dans `window.SIMON_SONS`. Le jeu les charge en **injectant
une balise `<script>`**, pas avec `fetch()`.

C'est le point à ne pas « simplifier ». Depuis `file://`, toute requête `fetch()`
ou XHR est refusée pour cause d'origine opaque, et les modules ES le sont aussi.
Une balise `<script>` classique vers un chemin relatif, elle, passe. C'est le
seul montage qui préserve la contrainte du projet : on ouvre le fichier et ça
marche, sans serveur. Vérifié sous Chromium en `file://`, douze paquets chargés,
aucune erreur console.

Les paquets pèsent 190 à 295 Ko chacun, 2,8 Mo au total, d'où le chargement à la
demande plutôt qu'un fichier unique. Ils **sont commités**, pour que le jeu
déployé ait ses vraies voix — voir Droits. Ils se régénèrent quand même d'une
commande si `assets/` est là :

```
python3 tools/fetch_dcr.py --out assets/        # si assets/ est vide
python3 tools/embarquer_sons.py --tout          # extrait puis embarque
```

Contraintes du prototype à conserver :

- Aucune dépendance à installer, aucun build. Un fichier qu'on ouvre.
- `localStorage` est autorisé — la contrainte « tourner dans un artifact Claude »
  a été levée, le site déployé étant devenu la cible principale. Mais il reste
  **facultatif** : tout accès est protégé et le jeu doit rester entièrement
  jouable quand le stockage est refusé. Voir « La persistance ».
- Accessible : focus clavier visible, `prefers-reduced-motion` respecté.

## Conventions

- Commentaires et messages de commit en français.
- Python 3 pour l'outillage, bibliothèque standard uniquement autant que possible.
  `zlib` et `struct` suffisent pour le parsing.
- Les binaires extraits vont dans `out/`, jamais commités.
- **Les `.dcr` d'origine restent hors du dépôt.** Le dépôt public ne contient que
  du code : outils, jeu, documentation. Les douze films sont l'œuvre de Joe Tree,
  et les commiter reviendrait à la republier — un dépôt local et un dépôt GitHub
  public ne sont pas la même chose, et l'historique Git survit aux forks.
  `tools/fetch_dcr.py` les récupère en une commande, donc on ne perd rien.
- Un contributeur part de zéro ainsi :
  `python3 tools/fetch_dcr.py --out assets/` puis
  `python3 tools/embarquer_sons.py --tout`.
- Un échec de parsing doit dire **quelle ressource** et **pourquoi**, pas remonter
  une exception nue.

## Droits

Les enregistrements et les images appartiennent à Joe Tree / Rocket Visuals
Limited. Le remake les utilise tels quels et les publie avec lui : choix assumé
de préservation, pris en connaissance de cause. Le jeu est mort avec Shockwave
en 2019 et ces voix n'existent plus nulle part ailleurs sous une forme jouable.

Ce que ça implique en pratique :

- **L'auteur est crédité là où on joue**, en pied de page du jeu et pas
  seulement dans un fichier de licence : nom, société, année, lien vers son site.
- **Rien n'est présenté comme nôtre.** Le remake est explicitement non officiel.
- **Retrait sur simple demande.** Si Joe Tree ou Rocket Visuals le souhaite, on
  retire les sons sans discuter. La mention figure dans le jeu et dans le README.
- Les `.dcr` d'origine, eux, restent hors du dépôt : voir Conventions.

## Arborescence

```
simon-swears/
├── CLAUDE.md
├── assets/                   # les treize .dcr, non commités
│   ├── loading.dcr           # l'écran de sélection de langue
│   └── simonswears*.dcr      # les douze films, un par langue
├── tools/
│   ├── fetch_dcr.py          # acquisition web + validation
│   ├── dcr_extract.py        # parser Afterburner
│   ├── extraire_sons.py      # snd  SWA -> mp3 nommés
│   ├── carte_touches.py      # restitue la carte couleur -> insulte
│   ├── nettoyer_voix.py      # prises des contributeurs -> mp3 propres
│   └── embarquer_sons.py     # mp3 -> paquets web/sons/<code>.js
├── out/                      # mp3 extraits, non commité
└── web/
    ├── simon-swears.html     # le jeu, avec les vrais sons
    └── sons/                 # paquets par langue, commités
```
