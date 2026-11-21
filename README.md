# Media Center

Un seul fichier Python, aucune dépendance. Liste tes films et ta musique, recherche, lecture dans le navigateur (avance/retour rapide, enchaînement automatique des morceaux).

## Installation (Windows)
1. Installer [Python 3](https://www.python.org/downloads/) (cocher « Add Python to PATH »).
2. Télécharger ce dossier.
3. Première fois, dans un terminal ouvert dans ce dossier :
   ```
   python mediacenter.py --films "D:\Films" --series "D:\Series" --musique "D:\Musique"
   ```
   (`--films` / `--series` / `--musique` répétables pour plusieurs dossiers ; on peut en ajouter un plus tard, les autres sont gardés.)
4. Ensuite : double-clic sur `MediaCenter.bat`. Le navigateur s'ouvre sur http://localhost:8765.

## Affiches et résumés
Au lancement, les affiches et résumés (en français) sont récupérés sur iTunes, gratuitement et sans compte, en arrière-plan : rafraîchis la page pour les voir apparaître. Comptez ~3 s par film la première fois (limite d'iTunes), ensuite tout est mémorisé dans `mediacenter_cache.json`. **Meilleure couverture avec TMDB (recommandé)** : crée un compte gratuit sur [themoviedb.org](https://www.themoviedb.org/signup), puis *Paramètres → API → Demander une clé* (usage personnel). Copie la « Clé d'API » (ou le « Jeton d'accès en lecture ») et lance une fois :
```
python mediacenter.py --tmdb TA_CLE
```
La clé est mémorisée dans `mediacenter.json`. TMDB est rapide (pas d'attente de 3 s) et repasse automatiquement sur les films déjà traités par iTunes.

Le titre est deviné à partir du nom du fichier (`Inception.2010.1080p.mkv` → *Inception*, 2010). Film mal reconnu : renomme le fichier `Titre (Année).mkv`, retire sa ligne de `mediacenter_cache.json` et relance.

## Séries TV
Les épisodes sont regroupés par série grâce au nom du fichier (`Breaking.Bad.S01E02…`, `Kaamelott 1x02…`) ou, à défaut, au nom du dossier de la série (`Series/Breaking Bad/Saison 1/…`). Clic sur une série → liste des épisodes dans l'ordre ; l'épisode suivant démarre automatiquement. Affiche et résumé de la série : TMDB si une clé est donnée, sinon iTunes.

## Reprise de lecture et « déjà vu »
Films et épisodes reprennent là où tu les as arrêtés (barre rouge sous le titre). Passé 90 % (générique), ils sont marqués **vus** ✓ ; clique sur le ✓ pour cocher/décocher à la main. Le suivi est enregistré sur le PC (`mediacenter_suivi.json`), donc partagé entre le PC, la TV et le téléphone en mode `--reseau`.

## Sous-titres
Les fichiers `.srt` / `.vtt` / `.ass` / `.ssa` sont détectés automatiquement : même nom que la vidéo (`Film.2020.srt`, `Film.2020.fr.srt`, `Film.2020.en.srt`) ou, si la vidéo est seule dans son dossier, tout `.srt` du dossier et d'un sous-dossier `Subs/`. Le français est activé par défaut ; change de langue ou coupe-les avec le bouton du lecteur (⋮ → Sous-titres, ou CC). Les accents des vieux `.srt` (Windows-1252) sont gérés.

**Animés (`.ass` / `.ssa`) : rendu stylé** avec [JASSUB](https://github.com/ThaUnknown/jassub) (libass, le moteur de VLC/mpv, en WebAssembly) : polices, couleurs, contours, positions, panneaux, karaoké, comme dans un lecteur dédié. Marche pour les `.ass` à côté de la vidéo et, avec ffmpeg, pour ceux intégrés aux MKV.
- Polices : celles jointes au MKV (extraites une fois dans `polices_cache/`) et celles d'un dossier `Fonts/` à côté de la vidéo ; sinon une police par défaut.
- Plein écran : bouton ⛶ en haut à droite de la vidéo ou double-clic (le plein écran natif du navigateur cacherait les sous-titres stylés).
- Navigateur trop ancien ou erreur : retour automatique aux sous-titres simples (texte + italique).

JASSUB est fourni dans le dossier `jassub/` (version 2.5.38, licence LGPL, voir `jassub/LICENSE`), pré-assemblé avec esbuild : rien à installer, marche sans internet.

**Sous-titres intégrés aux MKV** (et MP4) : installer [ffmpeg](https://ffmpeg.org) une fois, puis relancer :
```
winget install ffmpeg
```
Les pistes texte (SRT, ASS, …) apparaissent alors dans le menu sous-titres (« Français », « Anglais – SDH »…). Elles mettent quelques secondes à s'afficher la première fois (ffmpeg lit le fichier). Les sous-titres en image (PGS des Blu-ray, VobSub des DVD) ne peuvent pas être affichés par le navigateur.

## Lecture aléatoire et répéter tout (musique)
Bouton **⏮ Précédent** : si le morceau joue depuis plus de 3 s, il revient à son début ; sinon il passe au morceau d'avant (en aléatoire : celui joué juste avant). Bouton **⏭ Suivant** (les deux marchent aussi avec les touches ⏮ ⏭ du clavier ou du casque) : passe au morceau suivant en respectant l'aléatoire et « Répéter tout » ; en « Répéter 1 », il passe quand même au suivant, qui tourne alors en boucle. Bouton **🔀 Aléatoire** : chaque morceau est joué une fois dans un ordre au hasard, puis la lecture s'arrête. Bouton **🔁 Répéter**, à chaque clic : *Répéter tout* (à la fin de la liste, on recommence au début ; en aléatoire, nouveau tirage sans rejouer tout de suite le même morceau) → *🔂 Répéter 1* (le morceau en cours tourne en boucle) → désactivé. Les deux respectent la recherche (tape un artiste ou un album pour ne jouer que celui-ci) et restent activés au prochain lancement.

### Reprise du morceau en cours
Le morceau en cours et sa position sont mémorisés (dans le navigateur, par appareil). En revenant sur l'onglet Musique, après un rechargement ou au prochain lancement, il est prêt à la même seconde, **en pause** : appuie sur ▶ (les navigateurs interdisent de relancer le son tout seul).

### File d'attente
Le **+** au bout de chaque morceau l'ajoute à la fin de la file **À suivre** (affichée sous les boutons) ; le **↱** le place en tête (« lire juste après » : il passera dès la fin du morceau en cours). Ces morceaux passent avant la suite normale ou aléatoire, dans l'ordre d'ajout, même s'ils sont masqués par la recherche. Pour changer l'ordre, **glisse-dépose** un morceau sur un autre, ou utilise **↑ ↓** (clavier, écran tactile). Clic sur un morceau de la file : il joue tout de suite ; **×** le retire ; **Vider la file** efface tout. La file est sauvegardée dans le navigateur : elle survit au rechargement, au passage par Films/Séries et au redémarrage du Media Center (même si de nouveaux morceaux ont été ajoutés ; ceux supprimés entre-temps sont simplement retirés). Chaque appareil (PC, TV, téléphone) a sa propre file.

## Pochettes d'albums
Pour chaque dossier d'album, le Media Center utilise l'image présente dans le dossier (`cover.jpg`, `folder.jpg`, `front.png`… sinon la première image trouvée). À défaut, il prend la pochette intégrée aux fichiers (MP3, FLAC, M4A). S'il n'y en a toujours pas, il cherche la pochette sur iTunes d'après le nom du dossier (`Artiste - Album` ou `Artiste/Album`), en arrière-plan, et la mémorise dans `mediacenter_cache.json`.

Options : `--hors-ligne` (pas de recherche internet), `--port 9000`, `--reseau` (accès depuis la TV / le téléphone via `http://IP-du-PC:8765`).
Nouveaux fichiers téléchargés : relancer le programme pour rescanner.

## Limites
Le navigateur lit nativement MP4/WebM, MP3/FLAC/OGG/M4A/WAV. Les **MKV** passent dans Chrome/Edge si la vidéo est en H.264 ; les **AVI** et certains codecs audio (DTS, AC3) ne sont pas lus — pour ceux-là, utiliser VLC, ou [Jellyfin](https://jellyfin.org) qui transcode à la volée.
